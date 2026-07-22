import hashlib
import json
import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from ai_usage.models import AccountConfig, FetchStatus
from ai_usage.providers.base import ProviderError
from ai_usage.providers.claude import (
    ClaudeStatusProvider,
    ClaudeWebUsageProvider,
    canonical_claude_profile_dir,
    claude_cli_failure_message,
    claude_default_profile,
    claude_metric_model,
    claude_profile_path,
    claude_setup_required_message,
    extract_claude_notes,
    extract_claude_web_notes,
    install_status_relay,
    parse_claude_web_usage,
    parse_status_payload,
    parse_usage_output,
    remove_status_relay,
)
from ai_usage.providers.codex import (
    CodexStatusProvider,
    CodexWebUsageProvider,
    codex_model,
    extract_codex_notes,
    parse_codex_status,
    parse_codex_web_usage,
    parse_rate_limits,
)
from ai_usage.providers.copilot import CopilotBillingProvider, next_billing_reset


class FakeCurlResponse:
    """Stands in for a `curl_cffi.requests.Response` — respx only intercepts httpx, and
    curl_cffi has no equivalent transport-mocking hook, so tests fake the session directly."""

    def __init__(self, status_code: int, json_data) -> None:
        self.status_code = status_code
        self._json_data = json_data
    # end def

    def json(self):
        return self._json_data
    # end def

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")
        # end if
    # end def
# end class


class FakeCurlSession:
    """Stands in for `curl_cffi.requests.AsyncSession`."""

    def __init__(self, responses: dict[str, FakeCurlResponse], **kwargs) -> None:
        del kwargs
        self.responses = responses
    # end def

    async def __aenter__(self) -> FakeCurlSession:
        return self
    # end def

    async def __aexit__(self, *args) -> None:
        del args
    # end def

    async def get(self, path: str, headers=None, params=None) -> FakeCurlResponse:
        del headers, params
        return self.responses[path]
    # end def
# end class


def test_codex_app_server_rate_limits() -> None:
    now = datetime.now(UTC)
    metrics = parse_rate_limits(
        {
            "rateLimits": {
                "primary": {
                    "usedPercent": 25,
                    "windowDurationMins": 300,
                    "resetsAt": 1784300000,
                },
                "secondary": {
                    "usedPercent": 10,
                    "windowDurationMins": 10080,
                    "resetsAt": 1784900000,
                },
            }
        },
        now,
    )
    assert [metric.key for metric in metrics] == ["five-hours", "seven-days"]
    assert metrics[0].usage.percentage == 25
# end def


def test_codex_status_converts_remaining_to_used() -> None:
    output = "Weekly limit: [████░] 94% left (resets 12:36 on 24 Jul)"
    metrics = parse_codex_status(output, datetime.now(UTC))
    assert len(metrics) == 1
    assert metrics[0].usage.percentage == 6
# end def


@pytest.mark.asyncio
async def test_codex_status_provider_flags_stale_warning(monkeypatch) -> None:
    output = (
        "Weekly limit: [████░] 94% left (resets 12:36 on 24 Jul)\n"
        "Warning:              limits may be stale - run /status again shortly."
    )

    async def fake_run_codex_status(command: str) -> str:
        del command
        return output
    # end def

    monkeypatch.setattr(
        "ai_usage.providers.codex.run_codex_status", fake_run_codex_status
    )
    account = AccountConfig(id="a", service="codex", provider="cli-status", name="Codex")
    result = await CodexStatusProvider().fetch(account, None)
    assert result.status == FetchStatus.STALE
    assert result.error == "codex reported limits may be stale"
    assert len(result.metrics) == 1
# end def


def test_claude_status_line_payload() -> None:
    metrics = parse_status_payload(
        {
            "rate_limits": {
                "five_hour": {"used_percentage": 23.5, "resets_at": 1784300000},
                "seven_day": {"used_percentage": 41.2, "resets_at": 1784900000},
            }
        },
        datetime.now(UTC),
    )
    assert [metric.usage.percentage for metric in metrics] == [23.5, 41.2]
# end def


def test_claude_usage_output() -> None:
    output = """
Current session
  ███ 12% used
  Resets 7:50pm (Europe/Berlin)

Current week (all models)
  ████ 8% used
  Resets Jul 21, 10pm (Europe/Berlin)

Current week (Fable)
  0% used
  Resets Jul 21, 10pm (Europe/Berlin)
"""
    metrics = parse_usage_output(output, datetime.now(UTC))
    assert [metric.key for metric in metrics] == ["five-hours", "seven-days", "seven-days-fable"]
    assert [metric.usage.percentage for metric in metrics] == [12, 8, 0]
    assert [metric.model for metric in metrics] == [None, None, "Fable"]
# end def


def test_claude_usage_output_parses_cursor_positioned_terminal_text() -> None:
    output = (
        "Current\x1b[15Gsession\n"
        "\x1b[3G12%\x1b[8Gused\n"
        "Resets\x1b[15G7:50pm (Europe/Berlin)\n"
    )

    metrics = parse_usage_output(output, datetime.now(UTC))

    assert len(metrics) == 1
    assert metrics[0].key == "five-hours"
    assert metrics[0].usage.percentage == 12
# end def


def test_claude_cli_failure_reports_text_style_setup_from_recorded_transcript(
    caplog,
    monkeypatch,
    tmp_path,
) -> None:
    transcript_path = Path(__file__).parents[1] / "ai/errors/9.txt"
    transcript = transcript_path.read_text(encoding="utf-8")
    monkeypatch.setattr("ai_usage.providers.claude.CLAUDE_ERROR_LOG_DIR", tmp_path)

    with caplog.at_level(logging.ERROR, logger="ai_usage.providers.claude"):
        message = claude_cli_failure_message(transcript, "claude", "/profiles/claude")
    # end with

    assert message == (
        "Claude is waiting for first-run setup in /profiles/claude; run "
        "CLAUDE_CONFIG_DIR=/profiles/claude claude interactively, choose a text style, "
        "then retry the crawl."
    )
    error_log = tmp_path / (
        f"claude-cli.{hashlib.sha256(transcript.encode()).hexdigest()}.log"
    )
    assert error_log.read_text(encoding="utf-8") == transcript
    assert any(str(error_log) in message for message in caplog.messages)
# end def


def test_claude_cli_failure_keeps_generic_error_for_other_timeouts(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("ai_usage.providers.claude.CLAUDE_ERROR_LOG_DIR", tmp_path)

    message = claude_cli_failure_message("Claude is still starting\n", "claude", "/profiles/claude")
    assert message == (
        "Claude /usage did not become ready; use Claude once to refresh the status relay"
    )
# end def


def test_claude_default_profile_does_not_set_config_dir() -> None:
    default_profile = str(claude_default_profile())

    assert canonical_claude_profile_dir(None) is None
    assert canonical_claude_profile_dir(default_profile) is None
    assert claude_profile_path(None) == Path(default_profile)
    assert canonical_claude_profile_dir("/profiles/claude") == "/profiles/claude"
# end def


def test_claude_setup_message_uses_plain_command_for_default_profile() -> None:
    message = claude_setup_required_message(
        "Choose the text style that looks best with your terminal",
        "claude",
        str(claude_default_profile()),
    )

    assert message is not None
    assert "run claude interactively" in message
    assert "CLAUDE_CONFIG_DIR" not in message
# end def


def test_claude_metric_model_only_extracts_per_model_sections() -> None:
    assert claude_metric_model("Current session") is None
    assert claude_metric_model("Current week (all models)") is None
    assert claude_metric_model("Current week (Fable)") == "Fable"
# end def


def test_codex_model_extracted_from_motd_banner() -> None:
    output = (
        "model:     gpt-5.6-sol medium   /model to change\n"
        "Weekly limit: [████░] 94% left (resets 12:36 on 24 Jul)"
    )
    metrics = parse_codex_status(output, datetime.now(UTC))
    assert codex_model(output) == "gpt-5.6-sol medium"
    assert metrics[0].model == "gpt-5.6-sol medium"
# end def


def test_extract_claude_notes_finds_promo_banner() -> None:
    output = (
        "Current week (all models)\n"
        "████████████████████▌                              41% used\n"
        "Resets Jul 21, 10pm (Europe/Berlin)\n"
        "+50% weekly limits promo through Aug 19 · clau.de/cc-50-promo\n"
    )
    notes = extract_claude_notes(output)
    assert notes == ["+50% weekly limits promo through Aug 19 · clau.de/cc-50-promo"]
# end def


def test_extract_claude_notes_empty_without_promo() -> None:
    assert extract_claude_notes("Current session\n0% used\nResets 7:50pm (Europe/Berlin)\n") == []
# end def


def test_extract_codex_notes_finds_reset_availability_line() -> None:
    output = "• You have 3 usage limit resets available. Run /usage to use one.\n"
    assert extract_codex_notes(output) == ["You have 3 usage limit resets available. Run /usage to use one."]
# end def


def test_extract_claude_web_notes_finds_promo_banner() -> None:
    payload = {
        "org_growthbook": {
            "features": {
                "19186470": {
                    "defaultValue": {
                        "en-US": "**Your limits are boosted.** Weekly limit is 50% higher.",
                        "de-DE": "**Deine Limits sind vorübergehend erhöht.**",
                    }
                }
            }
        }
    }
    expected = ["**Your limits are boosted.** Weekly limit is 50% higher."]
    assert extract_claude_web_notes(payload) == expected
# end def


def test_extract_claude_web_notes_falls_back_to_any_locale_without_en_us() -> None:
    payload = {"org_growthbook": {"features": {"19186470": {"defaultValue": {"de-DE": "Erhöht."}}}}}
    assert extract_claude_web_notes(payload) == ["Erhöht."]
# end def


def test_extract_claude_web_notes_empty_when_feature_absent_or_malformed() -> None:
    assert extract_claude_web_notes({}) == []
    assert extract_claude_web_notes({"org_growthbook": {"features": {}}}) == []
    assert extract_claude_web_notes({"org_growthbook": {"features": {"19186470": {}}}}) == []
    assert extract_claude_web_notes(
        {"org_growthbook": {"features": {"19186470": {"defaultValue": "not-a-dict"}}}}
    ) == []
# end def


def test_claude_web_usage_payload() -> None:
    metrics = parse_claude_web_usage(
        {
            "five_hour": {"utilization": 16, "resets_at": "2026-07-18T14:40:00+00:00"},
            "seven_day": {"utilization": 28, "resets_at": "2026-07-21T20:00:00+00:00"},
        },
        datetime.now(UTC),
    )
    assert [metric.key for metric in metrics] == ["five-hours", "seven-days"]
    assert [metric.usage.percentage for metric in metrics] == [16, 28]
# end def


def test_claude_web_usage_payload_falls_back_on_schema_mismatch() -> None:
    metrics = parse_claude_web_usage(
        {"five_hour": {"utilization": "not-a-model-shape", "extra_nesting": {"x": 1}}},
        datetime.now(UTC),
    )
    assert metrics == []
# end def


@pytest.mark.asyncio
async def test_claude_web_usage_provider_collects_identity_and_subscription(monkeypatch) -> None:
    org_id = "e9abf7bc-490f-4c12-8490-d5b2d204e699"
    responses = {
        f"/api/organizations/{org_id}/usage": FakeCurlResponse(
            200,
            {
                "five_hour": {"utilization": 16, "resets_at": "2026-07-18T14:40:00+00:00"},
                "seven_day": {"utilization": 28, "resets_at": "2026-07-21T20:00:00+00:00"},
            },
        ),
        "/api/organizations": FakeCurlResponse(
            200,
            [
                {
                    "uuid": org_id,
                    "name": "AbelmannConsulting",
                    "billing_type": "stripe_subscription",
                }
            ],
        ),
        "/api/account": FakeCurlResponse(200, {"email_address": "user@example.com"}),
        f"/api/organizations/{org_id}/subscription_status": FakeCurlResponse(
            200, {"status": "active", "cancel_at_ts": None}
        ),
        f"/edge-api/bootstrap/{org_id}/app_start": FakeCurlResponse(
            200,
            {
                "org_growthbook": {
                    "features": {"19186470": {"defaultValue": {"en-US": "Limits boosted."}}}
                }
            },
        ),
    }
    monkeypatch.setattr(
        "ai_usage.providers.claude.AsyncSession",
        lambda **kwargs: FakeCurlSession(responses, **kwargs),
    )
    account = AccountConfig(
        id="account", service="claude", provider="web", name="Claude", options={"org_id": org_id}
    )
    result = await ClaudeWebUsageProvider().fetch(account, {"cookies": {"session": "x"}})
    assert [metric.usage.percentage for metric in result.metrics] == [16, 28]
    assert result.identity is not None
    assert result.identity.name == "AbelmannConsulting"
    assert result.identity.email == "user@example.com"
    assert result.subscription is not None
    assert result.subscription.plan_type == "stripe_subscription"
    assert result.subscription.status == "active"
    assert result.raw_payload is not None and "usage" in result.raw_payload
    assert result.raw_payload is not None and "app_start" in result.raw_payload
    assert result.notes == ["Limits boosted."]
# end def


@pytest.mark.asyncio
async def test_claude_web_usage_provider_notes_empty_when_app_start_fetch_fails(
    monkeypatch,
) -> None:
    org_id = "e9abf7bc-490f-4c12-8490-d5b2d204e699"
    responses = {
        f"/api/organizations/{org_id}/usage": FakeCurlResponse(
            200,
            {
                "five_hour": {"utilization": 16, "resets_at": "2026-07-18T14:40:00+00:00"},
                "seven_day": {"utilization": 28, "resets_at": "2026-07-21T20:00:00+00:00"},
            },
        ),
        "/api/organizations": FakeCurlResponse(200, []),
        "/api/account": FakeCurlResponse(404, {}),
        f"/api/organizations/{org_id}/subscription_status": FakeCurlResponse(404, {}),
        # app_start deliberately left unmapped so the fetch raises a KeyError, exercising the
        # best-effort try/except path — the whole fetch must not fail just because the
        # undocumented promo-banner probe did.
    }
    monkeypatch.setattr(
        "ai_usage.providers.claude.AsyncSession",
        lambda **kwargs: FakeCurlSession(responses, **kwargs),
    )
    account = AccountConfig(
        id="account", service="claude", provider="web", name="Claude", options={"org_id": org_id}
    )
    result = await ClaudeWebUsageProvider().fetch(account, {"cookies": {"session": "x"}})
    assert result.notes == []
# end def


@pytest.mark.asyncio
async def test_claude_web_discover_options_auto_fills_single_organization(monkeypatch) -> None:
    responses = {"/api/organizations": FakeCurlResponse(200, [{"uuid": "org-1", "name": "Solo"}])}
    monkeypatch.setattr(
        "ai_usage.providers.claude.AsyncSession",
        lambda **kwargs: FakeCurlSession(responses, **kwargs),
    )
    discovered = await ClaudeWebUsageProvider().discover_options({"cookies": {"session": "x"}})
    assert discovered == {"org_id": "org-1"}
# end def


@pytest.mark.asyncio
async def test_claude_web_discover_options_defaults_to_first_org_when_ambiguous(
    monkeypatch,
) -> None:
    responses = {
        "/api/organizations": FakeCurlResponse(
            200, [{"uuid": "org-1", "name": "Solo"}, {"uuid": "org-2", "name": "Team"}]
        ),
    }
    monkeypatch.setattr(
        "ai_usage.providers.claude.AsyncSession",
        lambda **kwargs: FakeCurlSession(responses, **kwargs),
    )
    discovered = await ClaudeWebUsageProvider().discover_options({"cookies": {"session": "x"}})
    assert discovered == {"org_id": "org-1"}
# end def


@pytest.mark.asyncio
async def test_claude_web_discover_options_returns_empty_without_cookies() -> None:
    assert await ClaudeWebUsageProvider().discover_options(None) == {}
    assert await ClaudeWebUsageProvider().discover_options({}) == {}
# end def


def test_codex_web_usage_payload() -> None:
    metrics = parse_codex_web_usage(
        {
            "rate_limit": {
                "primary_window": {
                    "used_percent": 0,
                    "limit_window_seconds": 604800,
                    "reset_at": 1784977190,
                },
                "secondary_window": None,
            }
        },
        datetime.now(UTC),
    )
    assert [metric.key for metric in metrics] == ["seven-days"]
    assert metrics[0].usage.percentage == 0
# end def


def test_codex_web_usage_payload_falls_back_on_schema_mismatch() -> None:
    metrics = parse_codex_web_usage({"rate_limit": "not-an-object"}, datetime.now(UTC))
    assert metrics == []
# end def


@pytest.mark.asyncio
async def test_codex_web_usage_provider_collects_identity_and_subscription(monkeypatch) -> None:
    responses = {
        "/api/auth/session": FakeCurlResponse(200, {"accessToken": "token-abc"}),
        "/backend-api/wham/usage": FakeCurlResponse(
            200,
            {
                "email": "user@example.com",
                "plan_type": "team",
                "rate_limit": {
                    "primary_window": {
                        "used_percent": 0,
                        "limit_window_seconds": 604800,
                        "reset_at": 1784977190,
                    }
                },
            },
        ),
    }
    monkeypatch.setattr(
        "ai_usage.providers.codex.AsyncSession",
        lambda **kwargs: FakeCurlSession(responses, **kwargs),
    )
    account = AccountConfig(id="account", service="codex", provider="web", name="Codex")
    result = await CodexWebUsageProvider().fetch(account, {"cookies": {"session": "x"}})
    assert len(result.metrics) == 1
    assert result.identity is not None and result.identity.email == "user@example.com"
    assert result.subscription is not None and result.subscription.plan_type == "team"
# end def


@pytest.mark.asyncio
async def test_claude_web_usage_provider_authenticate_captures_cookies(monkeypatch) -> None:
    monkeypatch.setattr(
        "ai_usage.providers.claude.capture_cookies_via_webview",
        lambda url, title: {"session": "abc"},
    )
    credential = await ClaudeWebUsageProvider().authenticate({})
    assert credential == {"cookies": {"session": "abc"}}
# end def


@pytest.mark.asyncio
async def test_claude_web_usage_provider_authenticate_returns_none_without_cookies(monkeypatch) -> None:
    monkeypatch.setattr(
        "ai_usage.providers.claude.capture_cookies_via_webview", lambda url, title: {}
    )
    assert await ClaudeWebUsageProvider().authenticate({}) is None
# end def


@pytest.mark.asyncio
async def test_codex_web_usage_provider_authenticate_captures_cookies(monkeypatch) -> None:
    calls: list[tuple[str, str, str | None]] = []

    def fake_capture(url, title, click_selector=None):
        calls.append((url, title, click_selector))
        return {"session": "xyz"}
    # end def

    monkeypatch.setattr("ai_usage.providers.codex.capture_cookies_via_webview", fake_capture)
    credential = await CodexWebUsageProvider().authenticate({})
    assert credential == {"cookies": {"session": "xyz"}}
    assert calls == [
        ("https://chatgpt.com/", "Codex private web API", '[data-testid="login-button"]')
    ]
# end def


def test_billing_reset_clamps_short_month() -> None:
    reset = next_billing_reset(datetime(2026, 2, 20, tzinfo=UTC), 31)
    assert reset == datetime(2026, 2, 28, tzinfo=UTC)
# end def


@pytest.mark.asyncio
@respx.mock
async def test_copilot_billing_provider() -> None:
    route = respx.get(
        "https://api.github.com/users/lucy/settings/billing/ai_credit/usage"
    ).mock(
        return_value=httpx.Response(
            200,
            json={"usageItems": [{"grossQuantity": 12.5}, {"grossQuantity": 7.5}]},
        )
    )
    account = AccountConfig(
        id="account",
        service="copilot",
        provider="github-api",
        name="Copilot",
        options={"username": "lucy", "allowance": 100, "billing_day": 1},
    )
    result = await CopilotBillingProvider().fetch(account, {"token": "github_pat_test"})
    assert route.called
    assert result.metrics[0].usage.percentage == 20
# end def


def relay_account(relay_file, **options) -> AccountConfig:
    return AccountConfig(
        id="relay-account",
        service="claude",
        provider="statusline",
        name="Claude",
        options={"relay_file": str(relay_file), **options},
    )
# end def


def write_relay(path, five_hour_percentage=23.5) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "rate_limits": {
                    "five_hour": {"used_percentage": five_hour_percentage, "resets_at": 1784300000},
                }
            }
        ),
        encoding="utf-8",
    )
# end def


@pytest.mark.asyncio
async def test_claude_status_fresh_relay_is_success(tmp_path) -> None:
    relay_file = tmp_path / "relay.json"
    write_relay(relay_file)
    account = relay_account(relay_file, stale_seconds=120)
    result = await ClaudeStatusProvider().fetch(account, None)
    assert result.status == FetchStatus.SUCCESS
    assert result.metrics[0].usage.percentage == 23.5
# end def


@pytest.mark.asyncio
async def test_claude_status_stale_relay_falls_back_to_cli_usage(tmp_path, monkeypatch) -> None:
    relay_file = tmp_path / "relay.json"
    write_relay(relay_file, five_hour_percentage=23.5)
    old = time.time() - 3600
    os.utime(relay_file, (old, old))
    account = relay_account(relay_file, stale_seconds=120)

    async def fake_run_claude_usage(*args, **kwargs):
        return "Current session\n  ██ 44% used\n  Resets 7:50pm (Europe/Berlin)\n"
    # end def

    monkeypatch.setattr("ai_usage.providers.claude.run_claude_usage", fake_run_claude_usage)
    result = await ClaudeStatusProvider().fetch(account, None)
    assert result.status == FetchStatus.SUCCESS
    assert result.metrics[0].usage.percentage == 44
# end def


@pytest.mark.asyncio
async def test_claude_status_missing_relay_falls_back_and_raises(tmp_path, monkeypatch) -> None:
    account = relay_account(tmp_path / "missing.json")

    async def raise_provider_error(*args, **kwargs):
        raise ProviderError("Claude /usage did not become ready; use Claude once to refresh the status relay")
    # end def

    monkeypatch.setattr("ai_usage.providers.claude.run_claude_usage", raise_provider_error)
    with pytest.raises(ProviderError, match="did not become ready"):
        await ClaudeStatusProvider().fetch(account, None)
# end def


def test_claude_relay_preserves_existing_command(tmp_path) -> None:
    profile = tmp_path / "claude"
    profile.mkdir()
    settings = profile / "settings.json"
    settings.write_text(
        '{"statusLine":{"type":"command","command":"existing-status"}}', encoding="utf-8"
    )
    account = AccountConfig(
        id="relay-account",
        service="claude",
        provider="statusline",
        name="Claude",
        options={"profile_dir": str(profile)},
    )
    local = tmp_path / "local"
    install_status_relay(account, local)
    assert "ai-usage-relay-relay-account" in settings.read_text(encoding="utf-8")
    relay_root = local / "claude-relay"
    assert (relay_root / "ai-usage-relay-relay-account.py").exists()
    remove_status_relay(account, local)
    assert "existing-status" in settings.read_text(encoding="utf-8")
    assert not (relay_root / "ai-usage-relay-relay-account.py").exists()
    assert not (relay_root / "relay-account.original.json").exists()
# end def


def test_claude_relay_uses_default_profile_for_null_option(tmp_path, monkeypatch) -> None:
    profile = tmp_path / "claude"
    profile.mkdir()
    monkeypatch.setattr("ai_usage.providers.claude.claude_default_profile", lambda: profile)
    account = AccountConfig(
        id="relay-account",
        service="claude",
        provider="statusline",
        name="Claude",
        options={"profile_dir": None},
    )

    install_status_relay(account, tmp_path / "local")

    assert (profile / "settings.json").exists()
# end def
