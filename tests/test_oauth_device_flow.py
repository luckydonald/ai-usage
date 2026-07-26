"""Tests for the RFC 8628 device-flow OAuth helper used by Kimi."""

import httpx
import pytest
import respx

from ai_usage.providers._shared.oauth_device_flow import run_device_flow_login
from ai_usage.providers.base import ProviderError


@pytest.mark.asyncio
@respx.mock
async def test_device_flow_succeeds_after_one_pending_poll(monkeypatch) -> None:
    respx.post("https://auth.example.com/device_authorization").mock(
        return_value=httpx.Response(
            200,
            json={
                "device_code": "dc",
                "user_code": "ABCD-1234",
                "verification_uri": "https://auth.example.com/activate",
                "interval": 0,
                "expires_in": 60,
            },
        )
    )
    token_route = respx.post("https://auth.example.com/token")
    token_route.side_effect = [
        httpx.Response(200, json={"error": "authorization_pending"}),
        httpx.Response(
            200, json={"access_token": "tok", "refresh_token": "ref", "expires_in": 3600}
        ),
    ]

    async def fast_sleep(_seconds: float) -> None:
        return None
    # end def

    monkeypatch.setattr("ai_usage.providers._shared.oauth_device_flow.asyncio.sleep", fast_sleep)

    prompts = []
    tokens = await run_device_flow_login(
        device_authorization_endpoint="https://auth.example.com/device_authorization",
        token_endpoint="https://auth.example.com/token",
        client_id="client",
        display_prompt=lambda code, uri: prompts.append((code, uri)),
    )
    assert tokens.access_token == "tok"
    assert tokens.refresh_token == "ref"
    assert prompts == [("ABCD-1234", "https://auth.example.com/activate")]
# end def


@pytest.mark.asyncio
@respx.mock
async def test_device_flow_raises_on_expired_token(monkeypatch) -> None:
    respx.post("https://auth.example.com/device_authorization").mock(
        return_value=httpx.Response(
            200,
            json={
                "device_code": "dc",
                "user_code": "ABCD-1234",
                "verification_uri": "https://auth.example.com/activate",
                "interval": 0,
                "expires_in": 60,
            },
        )
    )
    respx.post("https://auth.example.com/token").mock(
        return_value=httpx.Response(200, json={"error": "expired_token"})
    )

    async def fast_sleep(_seconds: float) -> None:
        return None
    # end def

    monkeypatch.setattr("ai_usage.providers._shared.oauth_device_flow.asyncio.sleep", fast_sleep)

    with pytest.raises(ProviderError):
        await run_device_flow_login(
            device_authorization_endpoint="https://auth.example.com/device_authorization",
            token_endpoint="https://auth.example.com/token",
            client_id="client",
            display_prompt=lambda code, uri: None,
        )
    # end with
# end def
