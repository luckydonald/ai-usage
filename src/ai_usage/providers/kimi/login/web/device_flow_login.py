"""Kimi (Moonshot) OAuth device-flow login."""

import platform
import re
import socket
import uuid
from typing import Any

from ai_usage.providers._shared.oauth_device_flow import run_device_flow_login
from ai_usage.providers.base import LoginMethod
from ai_usage.settings import Paths

DEVICE_AUTHORIZATION_ENDPOINT = "https://auth.kimi.com/api/oauth/device_authorization"
TOKEN_ENDPOINT = "https://auth.kimi.com/api/oauth/token"
CLIENT_ID = "17e5f671-d194-4dfb-9706-5516cb48c098"
KIMI_CLI_VERSION = "1.40.0"

_HOSTNAME_SANITIZE_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitized_hostname() -> str:
    return _HOSTNAME_SANITIZE_PATTERN.sub("-", socket.gethostname() or "unknown")
# end def


def _device_model() -> str:
    return f"{platform.system()} {platform.release()} {platform.machine()}"
# end def


def _persisted_device_id() -> str:
    path = Paths.from_environment().local / "kimi-device-id"
    if path.exists():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
        # end if
    # end if
    path.parent.mkdir(parents=True, exist_ok=True)
    generated = uuid.uuid4().hex
    path.write_text(generated, encoding="utf-8")
    return generated
# end def


def kimi_device_headers() -> dict[str, str]:
    return {
        "X-Msh-Platform": "kimi_cli",
        "X-Msh-Version": KIMI_CLI_VERSION,
        "X-Msh-Device-Name": _sanitized_hostname(),
        "X-Msh-Device-Model": _device_model(),
        "X-Msh-Os-Version": platform.version(),
        "X-Msh-Device-Id": _persisted_device_id(),
    }
# end def


class DeviceFlowLogin(LoginMethod):
    key = "oauth-device-flow"
    display_name = "Sign in via device code"
    credential_kind = "bearer_token"

    async def authenticate(self, options: dict[str, Any]) -> dict[str, Any] | None:
        del options
        tokens = await run_device_flow_login(
            device_authorization_endpoint=DEVICE_AUTHORIZATION_ENDPOINT,
            token_endpoint=TOKEN_ENDPOINT,
            client_id=CLIENT_ID,
            extra_headers=kimi_device_headers(),
        )
        credential: dict[str, Any] = {"token": tokens.access_token}
        if tokens.refresh_token:
            credential["refresh_token"] = tokens.refresh_token
        # end if
        return credential
    # end def
# end class
