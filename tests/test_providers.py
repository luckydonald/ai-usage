import json
import os
import time
from datetime import UTC, datetime

import httpx
import pytest
import respx

from ai_usage.models import AccountConfig, FetchStatus
from ai_usage.providers.base import ProviderError
from ai_usage.providers.claude import (
    ClaudeStatusProvider,
    ClaudeWebUsageProvider,
    install_status_relay,
    parse_claude_web_usage,
    parse_status_payload,
    parse_usage_output,
    remove_status_relay,
)
from ai_usage.providers.codex import (
    CodexStatusProvider,
    CodexWebUsageProvider,
    parse_codex_status,
    parse_codex_web_usage,
    parse_rate_limits,
)
from ai_usage.providers.copilot import CopilotBillingProvider, next_billing_reset


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
@respx.mock
async def test_claude_web_usage_provider_collects_identity_and_subscription() -> None:
    org_id = "e9abf7bc-490f-4c12-8490-d5b2d204e699"
    respx.get(f"https://claude.ai/api/organizations/{org_id}/usage").mock(
        return_value=httpx.Response(
            200,
            json={
                "five_hour": {"utilization": 16, "resets_at": "2026-07-18T14:40:00+00:00"},
                "seven_day": {"utilization": 28, "resets_at": "2026-07-21T20:00:00+00:00"},
            },
        )
    )
    respx.get("https://claude.ai/api/organizations").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "uuid": org_id,
                    "name": "AbelmannConsulting",
                    "billing_type": "stripe_subscription",
                }
            ],
        )
    )
    respx.get("https://claude.ai/api/account").mock(
        return_value=httpx.Response(200, json={"email_address": "user@example.com"})
    )
    respx.get(f"https://claude.ai/api/organizations/{org_id}/subscription_status").mock(
        return_value=httpx.Response(200, json={"status": "active", "cancel_at_ts": None})
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
# end def


@pytest.mark.asyncio
@respx.mock
async def test_claude_web_discover_options_auto_fills_single_organization() -> None:
    respx.get("https://claude.ai/api/organizations").mock(
        return_value=httpx.Response(200, json=[{"uuid": "org-1", "name": "Solo"}])
    )
    discovered = await ClaudeWebUsageProvider().discover_options({"cookies": {"session": "x"}})
    assert discovered == {"org_id": "org-1"}
# end def


@pytest.mark.asyncio
@respx.mock
async def test_claude_web_discover_options_defaults_to_first_org_when_ambiguous() -> None:
    respx.get("https://claude.ai/api/organizations").mock(
        return_value=httpx.Response(
            200,
            json=[{"uuid": "org-1", "name": "Solo"}, {"uuid": "org-2", "name": "Team"}],
        )
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
@respx.mock
async def test_codex_web_usage_provider_collects_identity_and_subscription() -> None:
    respx.get("https://chatgpt.com/api/auth/session").mock(
        return_value=httpx.Response(200, json={"accessToken": "token-abc"})
    )
    respx.get("https://chatgpt.com/backend-api/wham/usage").mock(
        return_value=httpx.Response(
            200,
            json={
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
        )
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
async def test_claude_status_stale_relay_skips_pexpect_fallback(tmp_path, monkeypatch) -> None:
    relay_file = tmp_path / "relay.json"
    write_relay(relay_file)
    old = time.time() - 3600
    os.utime(relay_file, (old, old))
    account = relay_account(relay_file, stale_seconds=120)

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("run_claude_usage should not be called when relay data exists")
    # end def

    monkeypatch.setattr("ai_usage.providers.claude.run_claude_usage", fail_if_called)
    result = await ClaudeStatusProvider().fetch(account, None)
    assert result.status == FetchStatus.STALE
    assert result.metrics[0].usage.percentage == 23.5
    assert "no new statusline data" in result.error
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
