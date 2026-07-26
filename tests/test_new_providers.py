"""Tests for the 8 new providers added on top of Claude/Codex/Copilot: Z.ai, MiniMax, Cline,
OpenRouter, Cursor, Ollama Cloud, SuperGrok, Kimi."""

from datetime import UTC, datetime

import httpx
import pytest
import respx

from ai_usage.models import AccountConfig
from ai_usage.providers.base import ProviderError, ProviderLoginError
from ai_usage.providers.cline.provider import ClineProvider
from ai_usage.providers.cline.usage.web.private_api import cline_micro_dollars_to_usd
from ai_usage.providers.cursor._shared import extract_cursor_bearer_token, extract_cursor_user_id
from ai_usage.providers.cursor.provider import CursorUsageProvider
from ai_usage.providers.cursor.usage.web.grpc_json import parse_current_period_usage
from ai_usage.providers.cursor.usage.web.private_api import cursor_cents_to_usd, parse_usage_summary
from ai_usage.providers.kimi.provider import KimiUsageProvider
from ai_usage.providers.kimi.usage.web.usages_api import (
    kimi_membership_display_name,
    kimi_session_window,
    parse_kimi_usages,
)
from ai_usage.providers.minimax.provider import MiniMaxProvider
from ai_usage.providers.minimax.usage.web.private_api import (
    minimax_normalize_timestamp,
    minimax_pick_used,
    parse_minimax_remains,
)
from ai_usage.providers.ollama.provider import OllamaCloudUsageProvider
from ai_usage.providers.ollama.usage.web.settings_scrape import (
    extract_ollama_plan,
    extract_ollama_reset_at,
    extract_ollama_usage_percentage,
    parse_ollama_settings_html,
)
from ai_usage.providers.openrouter.provider import OpenRouterProvider
from ai_usage.providers.supergrok.provider import SuperGrokBillingProvider
from ai_usage.providers.supergrok.usage.web.billing_api import (
    extract_billing_config,
    is_grok_billing_timeout,
    parse_supergrok_billing,
    unit_value,
)
from ai_usage.providers.zai.provider import ZaiProvider
from ai_usage.providers.zai.usage.web.private_api import parse_zai_limits, zai_period_ms


def account(service: str, provider: str, options: dict | None = None) -> AccountConfig:
    return AccountConfig(
        id="account", service=service, provider=provider, name="Test", options=options or {}
    )
# end def


# --- Z.ai -----------------------------------------------------------------------------------


def test_zai_period_ms_sorts_shortest_first() -> None:
    assert zai_period_ms(5, 30) < zai_period_ms(3, 1) < zai_period_ms(1, 1) < zai_period_ms(6, 1)
# end def


def test_parse_zai_limits_splits_session_weekly_and_web_search() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    payload = {
        "data": {
            "limits": [
                {
                    "type": "TOKENS_LIMIT", "unit": 6, "number": 1,
                    "currentValue": 10, "nextResetTime": None,
                },
                {"type": "TOKENS_LIMIT", "unit": 5, "number": 300, "currentValue": 40},
                {"type": "TIME_LIMIT", "unit": 1, "number": 1, "currentValue": 2},
            ]
        }
    }
    metrics = parse_zai_limits(payload, now)
    assert [metric.key for metric in metrics] == ["session", "weekly", "web-search"]
    assert metrics[0].usage.current == 40
# end def


@pytest.mark.asyncio
@respx.mock
async def test_zai_provider_raises_on_no_plan() -> None:
    respx.get("https://api.z.ai/api/biz/subscription/list").mock(
        return_value=httpx.Response(
            200, json={"success": False, "msg": "no coding plan found", "data": []}
        )
    )
    with pytest.raises(ProviderError):
        await ZaiProvider().fetch(account("zai", "api"), {"token": "key"})
    # end with
# end def


def test_zai_user_identity_always_raises() -> None:
    from ai_usage.models import ProviderFetchResult

    result = ProviderFetchResult(
        service="zai", provider="api", account_id="a", fetched_at=datetime.now(UTC)
    )
    with pytest.raises(ProviderLoginError):
        ZaiProvider().user_identity(account("zai", "api"), result)
    # end with
# end def


# --- MiniMax ----------------------------------------------------------------------------------


def test_minimax_normalize_timestamp_heuristic() -> None:
    assert minimax_normalize_timestamp(1_700_000_000) is not None
    assert minimax_normalize_timestamp(1_700_000_000_000) is not None
    assert minimax_normalize_timestamp(0) is None
# end def


def test_minimax_pick_used_prefers_usage_count() -> None:
    used, total = minimax_pick_used(
        {"current_interval_total_count": 100, "current_interval_usage_count": 30}
    )
    assert (used, total) == (30.0, 100.0)
# end def


def test_minimax_pick_used_falls_back_to_remaining() -> None:
    used, total = minimax_pick_used(
        {"current_interval_total_count": 100, "current_interval_remaining_count": 60}
    )
    assert (used, total) == (40.0, 100.0)
# end def


def test_parse_minimax_remains_builds_one_metric_per_entry() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    metrics = parse_minimax_remains(
        {
            "model_remains": [
                {
                    "plan_name": "Pro Plan",
                    "current_interval_total_count": 100,
                    "current_interval_usage_count": 25,
                }
            ]
        },
        now,
    )
    assert len(metrics) == 1
    assert metrics[0].usage.current == 25
# end def


@pytest.mark.asyncio
@respx.mock
async def test_minimax_provider_stops_on_auth_error() -> None:
    respx.get("https://api.minimax.io/v1/api/openplatform/coding_plan/remains").mock(
        return_value=httpx.Response(401)
    )
    minimax_account = account("minimax", "api", {"region": "global"})
    with pytest.raises(ProviderError):
        await MiniMaxProvider().fetch(minimax_account, {"token": "key"})
    # end with
# end def


@pytest.mark.asyncio
@respx.mock
async def test_minimax_provider_falls_back_through_region_urls() -> None:
    respx.get("https://api.minimax.io/v1/api/openplatform/coding_plan/remains").mock(
        return_value=httpx.Response(500)
    )
    respx.get("https://api.minimax.io/v1/coding_plan/remains").mock(
        return_value=httpx.Response(
            200,
            json={
                "base_resp": {"status_code": 0},
                "model_remains": [
                    {
                        "plan_name": "Pro",
                        "current_interval_total_count": 10,
                        "current_interval_usage_count": 3,
                    }
                ],
            },
        )
    )
    minimax_account = account("minimax", "api", {"region": "global"})
    result = await MiniMaxProvider().fetch(minimax_account, {"token": "key"})
    assert result.metrics[0].usage.current == 3
# end def


# --- Cline ------------------------------------------------------------------------------------


def test_cline_micro_dollars_conversion() -> None:
    assert cline_micro_dollars_to_usd(1_500_000) == 1.5
# end def


@pytest.mark.asyncio
@respx.mock
async def test_cline_provider_combines_endpoints_best_effort() -> None:
    respx.get("https://api.cline.bot/api/v1/users/me").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"id": "user-1"}})
    )
    respx.get("https://api.cline.bot/api/v1/users/user-1/balance").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"balance": 2_000_000}})
    )
    respx.get("https://api.cline.bot/api/v1/users/user-1/usages").mock(
        return_value=httpx.Response(500)
    )
    respx.get("https://api.cline.bot/api/v1/users/me/plan/usage-limits").mock(
        return_value=httpx.Response(
            200,
            json={"success": True, "data": {"limits": [{"type": "weekly", "percentUsed": 42}]}},
        )
    )
    result = await ClineProvider().fetch(account("cline", "api"), {"token": "key"})
    keys = [metric.key for metric in result.metrics]
    assert "balance" in keys
    assert "clinepass-weekly" in keys
    assert "tokens-used" not in keys
    assert ClineProvider().user_identity(account("cline", "api"), result) == "user-1"
# end def


@pytest.mark.asyncio
@respx.mock
async def test_cline_provider_raises_on_invalid_key() -> None:
    respx.get("https://api.cline.bot/api/v1/users/me").mock(return_value=httpx.Response(401))
    with pytest.raises(ProviderError):
        await ClineProvider().fetch(account("cline", "api"), {"token": "bad"})
    # end with
# end def


# --- OpenRouter -------------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_openrouter_provider_computes_remaining() -> None:
    respx.get("https://openrouter.ai/api/v1/credits").mock(
        return_value=httpx.Response(200, json={"data": {"total_credits": 100, "total_usage": 40}})
    )
    respx.get("https://openrouter.ai/api/v1/activity").mock(
        return_value=httpx.Response(
            200, json={"data": [{"prompt_tokens": 10, "completion_tokens": 5}]}
        )
    )
    result = await OpenRouterProvider().fetch(account("openrouter", "api"), {"token": "key"})
    credits_metric = next(m for m in result.metrics if m.key == "credits")
    assert credits_metric.usage.current == 40
    tokens_metric = next(m for m in result.metrics if m.key == "tokens-used")
    assert tokens_metric.usage.current == 15
# end def


def test_openrouter_user_identity_always_raises() -> None:
    from ai_usage.models import ProviderFetchResult

    result = ProviderFetchResult(
        service="openrouter", provider="api", account_id="a", fetched_at=datetime.now(UTC)
    )
    with pytest.raises(ProviderLoginError):
        OpenRouterProvider().user_identity(account("openrouter", "api"), result)
    # end with
# end def


# --- Cursor -----------------------------------------------------------------------------------


def test_extract_cursor_bearer_token_from_compound_cookie() -> None:
    cookies = {"WorkosCursorSessionToken": "user-123%3A%3AeyJhbGciOiJIUzI1NiJ9.payload.sig"}
    assert extract_cursor_bearer_token(cookies) == "eyJhbGciOiJIUzI1NiJ9.payload.sig"
    assert extract_cursor_user_id(cookies) == "user-123"
# end def


def test_extract_cursor_bearer_token_bare_jwt() -> None:
    cookies = {"WorkosCursorSessionToken": "eyJhbGciOiJIUzI1NiJ9.payload.sig"}
    assert extract_cursor_bearer_token(cookies) == "eyJhbGciOiJIUzI1NiJ9.payload.sig"
# end def


def test_cursor_cents_to_usd() -> None:
    assert cursor_cents_to_usd(1234) == 12.34
# end def


def test_parse_usage_summary_reads_plan_usage() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    metrics = parse_usage_summary(
        {"individualUsage": {"plan": {"used": 500, "limit": 2000}}}, now
    )
    assert metrics[0].usage.current == 5.0
    assert metrics[0].usage.maximum == 20.0
# end def


def test_parse_current_period_usage_reads_plan_usage() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    metrics = parse_current_period_usage({"planUsage": {"totalSpend": 100, "limit": 1000}}, now)
    assert metrics[0].usage.current == 1.0
# end def


def test_cursor_user_identity_raises_without_identity() -> None:
    from ai_usage.models import ProviderFetchResult

    result = ProviderFetchResult(
        service="cursor", provider="web", account_id="a", fetched_at=datetime.now(UTC)
    )
    with pytest.raises(ProviderLoginError):
        CursorUsageProvider().user_identity(account("cursor", "web"), result)
    # end with
# end def


# --- Ollama Cloud -------------------------------------------------------------------------------

OLLAMA_SETTINGS_HTML = """
<html><body>
<h2>Cloud Usage</h2>
<div><span class="capitalize">pro</span></div>
<div>
  <span class="text-sm">Session usage</span>
  <div style="width: 42.5%"></div>
  <span data-time="2026-02-01T00:00:00+00:00"></span>
</div>
<div>
  <span class="text-sm">Weekly usage</span>
  <div style="width: 10%"></div>
  <span data-time="2026-02-07T00:00:00+00:00"></span>
</div>
</body></html>
"""


def test_ollama_html_extraction() -> None:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(OLLAMA_SETTINGS_HTML, "html.parser")
    assert extract_ollama_plan(soup) == "pro"
    assert extract_ollama_usage_percentage(soup, "Session usage") == 42.5
    assert extract_ollama_usage_percentage(soup, "Weekly usage") == 10.0
    assert extract_ollama_reset_at(soup, "Session usage") is not None
# end def


def test_parse_ollama_settings_html_builds_metrics() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    metrics = parse_ollama_settings_html(OLLAMA_SETTINGS_HTML, now)
    assert [metric.key for metric in metrics] == ["session", "weekly"]
# end def


def test_parse_ollama_settings_html_empty_on_layout_change() -> None:
    metrics = parse_ollama_settings_html(
        "<html><body>nothing here</body></html>", datetime.now(UTC)
    )
    assert metrics == []
# end def


@pytest.mark.asyncio
@respx.mock
async def test_ollama_provider_fails_loudly_on_layout_change() -> None:
    respx.get("https://ollama.com/settings").mock(
        return_value=httpx.Response(200, text="<html><body>unexpected</body></html>")
    )
    with pytest.raises(ProviderError):
        await OllamaCloudUsageProvider().fetch(
            account("ollama", "web"), {"cookies": {"__Secure-session": "s"}}
        )
    # end with
# end def


# --- SuperGrok --------------------------------------------------------------------------------


def test_unit_value_handles_raw_and_wrapped_numbers() -> None:
    assert unit_value({"used": 5}, "used") == 5.0
    assert unit_value({"used": {"val": 7}}, "used") == 7.0
    assert unit_value({}, "used") is None
# end def


def test_extract_billing_config_handles_both_roots() -> None:
    assert extract_billing_config({"config": {"a": 1}}) == {"a": 1}
    assert extract_billing_config({"billing": {"config": {"a": 1}}}) == {"a": 1}
# end def


def test_is_grok_billing_timeout() -> None:
    assert is_grok_billing_timeout(
        400, {"code": "The operation was cancelled", "error": "Timeout expired"}
    )
    assert not is_grok_billing_timeout(400, {"code": "other", "error": "Timeout expired"})
    assert not is_grok_billing_timeout(500, {})
# end def


def test_parse_supergrok_billing_computes_used_from_percent() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    metrics = parse_supergrok_billing({"monthlyLimit": 200, "creditUsagePercent": 25.0}, now)
    assert metrics[0].usage.current == 50.0
# end def


@pytest.mark.asyncio
@respx.mock
async def test_supergrok_provider_raises_without_identity_hint() -> None:
    respx.get("https://cli-chat-proxy.grok.com/v1/billing").mock(
        return_value=httpx.Response(200, json={"config": {"used": 10, "monthlyLimit": 100}})
    )
    respx.get("https://cli-chat-proxy.grok.com/v1/settings").mock(return_value=httpx.Response(404))
    result = await SuperGrokBillingProvider().fetch(account("supergrok", "web"), {"token": "key"})
    assert result.metrics[0].usage.current == 10
    with pytest.raises(ProviderLoginError):
        SuperGrokBillingProvider().user_identity(account("supergrok", "web"), result)
    # end with
# end def


@pytest.mark.asyncio
@respx.mock
async def test_supergrok_provider_uses_identity_hint_from_credential() -> None:
    respx.get("https://cli-chat-proxy.grok.com/v1/billing").mock(
        return_value=httpx.Response(200, json={"config": {"used": 10, "monthlyLimit": 100}})
    )
    respx.get("https://cli-chat-proxy.grok.com/v1/settings").mock(return_value=httpx.Response(404))
    credential = {"token": "key", "identity_hint": "person@example.com"}
    result = await SuperGrokBillingProvider().fetch(account("supergrok", "web"), credential)
    login = SuperGrokBillingProvider().user_identity(account("supergrok", "web"), result)
    assert login == "person@example.com"
# end def


# --- Kimi -------------------------------------------------------------------------------------


def test_kimi_session_window_prefers_five_minute_window() -> None:
    limits = [
        {"window": {"duration": 3600, "timeUnit": "TIME_UNIT_HOUR"}, "detail": {}},
        {"window": {"duration": 300, "timeUnit": "TIME_UNIT_MINUTE"}, "detail": {"limit": "1"}},
    ]
    assert kimi_session_window(limits)["detail"]["limit"] == "1"
# end def


def test_kimi_session_window_falls_back_to_first() -> None:
    limits = [
        {"window": {"duration": 3600, "timeUnit": "TIME_UNIT_HOUR"}, "detail": {"limit": "9"}}
    ]
    assert kimi_session_window(limits)["detail"]["limit"] == "9"
# end def


def test_parse_kimi_usages_handles_string_fields() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    payload = {
        "limits": [
            {
                "window": {"duration": 300, "timeUnit": "TIME_UNIT_MINUTE"},
                "detail": {"limit": "100", "remaining": "60"},
            }
        ]
    }
    metrics = parse_kimi_usages(payload, now)
    assert metrics[0].usage.current == 40.0
    assert metrics[0].usage.maximum == 100.0
# end def


def test_kimi_membership_display_name() -> None:
    assert kimi_membership_display_name("LEVEL_ADVANCED") == "Kimi Code Advanced"
    assert kimi_membership_display_name("LEVEL_UNKNOWN_TIER") == "Kimi Code Unknown Tier"
    assert kimi_membership_display_name(None) is None
# end def


@pytest.mark.asyncio
@respx.mock
async def test_kimi_provider_user_identity_always_raises() -> None:
    respx.get("https://api.kimi.com/coding/v1/usages").mock(
        return_value=httpx.Response(
            200,
            json={
                "limits": [
                    {
                        "window": {"duration": 300, "timeUnit": "TIME_UNIT_MINUTE"},
                        "detail": {"limit": "10", "remaining": "5"},
                    }
                ],
                "user": {"membership": {"level": "LEVEL_PREMIUM"}},
            },
        )
    )
    result = await KimiUsageProvider().fetch(account("kimi", "web"), {"token": "key"})
    assert result.subscription.plan_type == "Kimi Code Premium"
    with pytest.raises(ProviderLoginError):
        KimiUsageProvider().user_identity(account("kimi", "web"), result)
    # end with
# end def
