from datetime import UTC, datetime

import httpx
import pytest
import respx

from ai_usage.models import AccountConfig
from ai_usage.providers.claude import (
    install_status_relay,
    parse_status_payload,
    parse_usage_output,
    remove_status_relay,
)
from ai_usage.providers.codex import parse_codex_status, parse_rate_limits
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
    remove_status_relay(account, local)
    assert "existing-status" in settings.read_text(encoding="utf-8")
# end def
