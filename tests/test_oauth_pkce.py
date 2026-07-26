"""Tests for the PKCE + local-loopback-callback OAuth helper used by SuperGrok."""

import asyncio
import socket
import urllib.parse
from typing import Any

import httpx
import pytest

from ai_usage.providers._shared.oauth_pkce import run_pkce_login
from ai_usage.providers.base import ProviderError


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    # end with
# end def


class _FakeTokenResponse:
    status_code = 200

    def json(self) -> dict[str, Any]:
        return {"access_token": "tok", "id_token": "idtok"}
    # end def
# end class


@pytest.mark.asyncio
async def test_pkce_login_completes_after_simulated_browser_callback(monkeypatch) -> None:
    # respx intercepts at the transport level, which also swallows the real loopback GET this
    # test issues against `run_pkce_login`'s own local callback server (no reliable pass-through
    # for that in this environment) — so the token-exchange POST is faked directly instead.
    async def fake_post(self, url: str, data: Any = None, **kwargs: Any) -> _FakeTokenResponse:
        del self, url, data, kwargs
        return _FakeTokenResponse()
    # end def

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    port = _free_port()
    redirect_uri = f"http://127.0.0.1:{port}/callback"
    captured_urls = []

    def fake_open(url: str) -> bool:
        captured_urls.append(url)
        return True
    # end def

    monkeypatch.setattr("ai_usage.providers._shared.oauth_pkce.webbrowser.open", fake_open)

    login_task = asyncio.create_task(
        run_pkce_login(
            authorization_endpoint="https://auth.example.com/authorize",
            token_endpoint="https://auth.example.com/token",
            client_id="client",
            redirect_uri=redirect_uri,
            scopes=("openid",),
            callback_timeout=8,
        )
    )

    # Wait for the fake browser to have been "opened" (server bound + authorize URL built).
    for _ in range(50):
        if captured_urls:
            break
        # end if
        await asyncio.sleep(0.05)
    # end for
    assert captured_urls, "run_pkce_login never opened the authorize URL"
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(captured_urls[0]).query)
    state = query["state"][0]

    async with httpx.AsyncClient() as client:
        await client.get(redirect_uri, params={"code": "authcode", "state": state})
    # end async with

    exchange = await asyncio.wait_for(login_task, timeout=10)
    assert exchange.access_token == "tok"
    assert exchange.id_token == "idtok"
# end def


@pytest.mark.asyncio
async def test_pkce_login_rejects_state_mismatch(monkeypatch) -> None:
    port = _free_port()
    redirect_uri = f"http://127.0.0.1:{port}/callback"

    def fake_open(url: str) -> bool:
        return True
    # end def

    monkeypatch.setattr("ai_usage.providers._shared.oauth_pkce.webbrowser.open", fake_open)

    login_task = asyncio.create_task(
        run_pkce_login(
            authorization_endpoint="https://auth.example.com/authorize",
            token_endpoint="https://auth.example.com/token",
            client_id="client",
            redirect_uri=redirect_uri,
            scopes=("openid",),
            callback_timeout=8,
        )
    )
    await asyncio.sleep(0.2)
    async with httpx.AsyncClient() as client:
        await client.get(redirect_uri, params={"code": "authcode", "state": "wrong-state"})
    # end async with

    with pytest.raises(ProviderError):
        await asyncio.wait_for(login_task, timeout=10)
    # end with
# end def
