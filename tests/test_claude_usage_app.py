"""Tests for the ClaudeUsage.app local-API Claude provider."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from ai_usage.models import AccountConfig, AccountIdentity
from ai_usage.providers.base import ProviderError, ProviderLoginError
from ai_usage.providers.claude.login.local.usage_app import UsageAppLogin
from ai_usage.providers.claude.provider import ClaudeUsageAppProvider
from ai_usage.providers.claude.usage.local.usage_app import DEFAULT_BASE_URL
from ai_usage.providers.registry import built_in_registry

AUTH_STATUS = "ai_usage.providers.claude.usage.local.usage_app.run_claude_auth_status"


def account(options: dict | None = None) -> AccountConfig:
    return AccountConfig(
        id="account",
        service="claude",
        provider="claude-usage-app-api",
        name="Test",
        options=options or {},
    )
# end def


def window(percent: float, updated: datetime | None = None) -> dict:
    return {
        "lastUpdated": (updated or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "email",
        "available": True,
        "percentUsed": percent,
        "percentRemaining": 100 - percent,
        "resetsAt": "2026-10-06T12:39:59Z",
        "resetsInSeconds": 17343,
    }
# end def


UNAVAILABLE = {"error": "window_unavailable", "message": "no window", "available": False}


def mock_windows(session=None, weekly=None, opus=None) -> None:
    for path, body in (("session", session), ("weekly", weekly), ("opus", opus)):
        if body is None:
            respx.get(f"{DEFAULT_BASE_URL}/{path}").mock(return_value=httpx.Response(404, json=UNAVAILABLE))
        else:
            respx.get(f"{DEFAULT_BASE_URL}/{path}").mock(return_value=httpx.Response(200, json=body))
        # end if
    # end for
# end def


@pytest.mark.asyncio
@respx.mock
async def test_fetch_maps_all_windows(monkeypatch) -> None:
    mock_windows(window(3), window(40), window(12.5))
    monkeypatch.setattr(AUTH_STATUS, _auth("me@example.com"))
    result = await ClaudeUsageAppProvider().fetch(account(), None)
    by_key = {metric.key: metric for metric in result.metrics}
    assert set(by_key) == {"five-hours", "seven-days", "seven-days-opus"}
    assert by_key["five-hours"].usage.percentage == 3
    assert by_key["five-hours"].window_seconds == 18000
    assert by_key["five-hours"].reset_at == datetime(2026, 10, 6, 12, 39, 59, tzinfo=UTC)
    assert by_key["seven-days-opus"].model == "Opus"
    assert by_key["seven-days-opus"].window_seconds == 604800
    assert result.identity is not None and result.identity.email == "me@example.com"
    assert result.notes == []
# end def


@pytest.mark.asyncio
@respx.mock
async def test_fetch_skips_unavailable_window(monkeypatch) -> None:
    mock_windows(None, window(40), None)
    monkeypatch.setattr(AUTH_STATUS, _auth(None))
    result = await ClaudeUsageAppProvider().fetch(account({"email": "a@b.c"}), None)
    assert [metric.key for metric in result.metrics] == ["seven-days"]
# end def


@pytest.mark.asyncio
@respx.mock
async def test_fetch_without_any_window_raises() -> None:
    mock_windows()
    with pytest.raises(ProviderError, match="no usage windows"):
        await ClaudeUsageAppProvider().fetch(account({"email": "a@b.c"}), None)
# end def


@pytest.mark.asyncio
@respx.mock
async def test_fetch_no_data_raises() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/session").mock(
        return_value=httpx.Response(503, json={"error": "no_data", "message": "x"})
    )
    with pytest.raises(ProviderError, match="no cached usage"):
        await ClaudeUsageAppProvider().fetch(account(), None)
# end def


@pytest.mark.asyncio
@respx.mock
async def test_fetch_app_not_running_raises() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/session").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(ProviderError, match="Local API"):
        await ClaudeUsageAppProvider().fetch(account(), None)
# end def


@pytest.mark.asyncio
@respx.mock
async def test_fetch_honours_base_url_and_notes_stale_data() -> None:
    old = datetime.now(UTC) - timedelta(hours=1)
    respx.get("http://127.0.0.1:1234/session").mock(return_value=httpx.Response(200, json=window(1, old)))
    respx.get("http://127.0.0.1:1234/weekly").mock(return_value=httpx.Response(404, json=UNAVAILABLE))
    respx.get("http://127.0.0.1:1234/opus").mock(return_value=httpx.Response(404, json=UNAVAILABLE))
    result = await ClaudeUsageAppProvider().fetch(
        account({"base_url": "http://127.0.0.1:1234", "email": "a@b.c"}), None
    )
    assert len(result.notes) == 1 and "backgrounded" in result.notes[0]
# end def


@pytest.mark.asyncio
@respx.mock
async def test_identity_prefers_email_option_over_cli(monkeypatch) -> None:
    mock_windows(window(3), None, None)
    monkeypatch.setattr(AUTH_STATUS, _auth("cli@example.com"))
    provider = ClaudeUsageAppProvider()
    configured = account({"email": "Me@Example.com"})
    result = await provider.fetch(configured, None)
    assert provider.user_identity(configured, result) == "me@example.com"
# end def


@pytest.mark.asyncio
@respx.mock
async def test_identity_falls_back_to_cli_then_raises(monkeypatch) -> None:
    mock_windows(window(3), None, None)
    provider = ClaudeUsageAppProvider()
    monkeypatch.setattr(AUTH_STATUS, _auth("cli@example.com"))
    result = await provider.fetch(account(), None)
    assert provider.user_identity(account(), result) == "cli@example.com"
    monkeypatch.setattr(AUTH_STATUS, _auth(None))
    result = await provider.fetch(account(), None)
    with pytest.raises(ProviderLoginError, match="--email"):
        provider.user_identity(account(), result)
# end def


@pytest.mark.asyncio
@respx.mock
async def test_login_discovers_running_app() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/health").mock(
        return_value=httpx.Response(200, json={"ok": True, "lastUpdated": None, "uptimeSeconds": 1})
    )
    found = await UsageAppLogin().discover()
    assert [item.options for item in found] == [{"base_url": DEFAULT_BASE_URL}]
# end def


@pytest.mark.asyncio
@respx.mock
async def test_login_discovers_nothing_when_app_is_down() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/health").mock(side_effect=httpx.ConnectError("refused"))
    assert await UsageAppLogin().discover() == []
# end def


def test_provider_is_registered() -> None:
    provider = built_in_registry().get("claude", "claude-usage-app-api")
    assert provider.experimental
    assert provider.matching_login_methods()
# end def


def _auth(email: str | None):
    async def fake(command: str, profile_dir: str | None) -> AccountIdentity | None:
        return AccountIdentity(email=email) if email else None
    # end def

    return fake
# end def
