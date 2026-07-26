"""Generic OAuth 2.0 Device Authorization Grant (RFC 8628) login.

Used by Kimi (Moonshot); the vendor's own client id/endpoints/extra headers are passed in by
the caller, this module only implements the RFC 8628 state machine.
"""

import asyncio
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import click
import httpx

from ai_usage.providers.base import ProviderError

DEFAULT_POLL_TIMEOUT_SECONDS = 600.0


@dataclass(frozen=True)
class DeviceFlowTokens:
    access_token: str
    refresh_token: str | None
    expires_in: int | None
    raw: dict[str, Any]
# end class


def _default_display_prompt(user_code: str, verification_uri: str) -> None:
    click.echo(f"Go to {verification_uri} and enter code: {user_code}")
    try:
        webbrowser.open(verification_uri)
    except Exception:  # noqa: BLE001
        pass
    # end try
# end def


async def run_device_flow_login(
    *,
    device_authorization_endpoint: str,
    token_endpoint: str,
    client_id: str,
    scope: str | None = None,
    extra_headers: dict[str, str] | None = None,
    display_prompt: Callable[[str, str], None] = _default_display_prompt,
    poll_timeout: float = DEFAULT_POLL_TIMEOUT_SECONDS,
) -> DeviceFlowTokens:
    headers = extra_headers or {}
    async with httpx.AsyncClient(timeout=20, headers=headers) as client:
        device_data = {"client_id": client_id}
        if scope:
            device_data["scope"] = scope
        # end if
        device_response = await client.post(device_authorization_endpoint, data=device_data)
        if device_response.status_code != 200:
            raise ProviderError(
                f"device authorization request failed: HTTP {device_response.status_code}"
            )
        # end if
        device_payload: dict[str, Any] = device_response.json()
        device_code = device_payload.get("device_code")
        user_code = device_payload.get("user_code")
        verification_uri = device_payload.get("verification_uri_complete") or device_payload.get(
            "verification_uri"
        )
        if not device_code or not user_code or not verification_uri:
            raise ProviderError("device authorization response missing required fields")
        # end if
        interval = float(device_payload.get("interval") or 5)
        expires_in = float(device_payload.get("expires_in") or poll_timeout)
        deadline = min(expires_in, poll_timeout)

        display_prompt(user_code, verification_uri)

        elapsed = 0.0
        while elapsed < deadline:
            await asyncio.sleep(interval)
            elapsed += interval
            token_response = await client.post(
                token_endpoint,
                data={
                    "client_id": client_id,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
            )
            token_payload: dict[str, Any] = token_response.json()
            error = token_payload.get("error")
            if error is None and token_payload.get("access_token"):
                return DeviceFlowTokens(
                    access_token=token_payload["access_token"],
                    refresh_token=token_payload.get("refresh_token"),
                    expires_in=token_payload.get("expires_in"),
                    raw=token_payload,
                )
            # end if
            if error == "authorization_pending":
                continue
            # end if
            if error == "slow_down":
                interval += 5
                continue
            # end if
            raise ProviderError(f"device-flow login failed: {error or token_response.status_code}")
        # end while
        raise ProviderError("timed out waiting for the user to approve the device-flow login")
    # end async with
# end def
