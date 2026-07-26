"""xAI OAuth PKCE login for SuperGrok."""

import base64
import json
from typing import Any

from ai_usage.providers._shared.oauth_pkce import run_pkce_login
from ai_usage.providers.base import LoginMethod

AUTHORIZATION_ENDPOINT = "https://auth.x.ai/oauth2/authorize"
TOKEN_ENDPOINT = "https://auth.x.ai/oauth2/token"
CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
REDIRECT_URI = "http://127.0.0.1:56121/callback"
SCOPES = ("openid", "profile", "email", "offline_access", "grok-cli:access", "api:access")
EXTRA_AUTHORIZE_PARAMS = {"plan": "generic", "referrer": "openai-usage-quota-plugin"}


def _decode_jwt_claims(token: str) -> dict[str, Any]:
    try:
        payload_segment = token.split(".")[1]
        padding = "=" * (-len(payload_segment) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_segment + padding))
    except Exception:  # noqa: BLE001
        return {}
    # end try
# end def


class PkceLogin(LoginMethod):
    key = "oauth-pkce"
    display_name = "Sign in via browser (xAI OAuth)"
    credential_kind = "bearer_token"

    async def authenticate(self, options: dict[str, Any]) -> dict[str, Any] | None:
        del options
        exchange = await run_pkce_login(
            authorization_endpoint=AUTHORIZATION_ENDPOINT,
            token_endpoint=TOKEN_ENDPOINT,
            client_id=CLIENT_ID,
            redirect_uri=REDIRECT_URI,
            scopes=SCOPES,
            extra_authorize_params=EXTRA_AUTHORIZE_PARAMS,
            include_nonce=True,
        )
        credential: dict[str, Any] = {"token": exchange.access_token}
        if exchange.refresh_token:
            credential["refresh_token"] = exchange.refresh_token
        # end if
        if exchange.id_token:
            claims = _decode_jwt_claims(exchange.id_token)
            identity_hint = claims.get("email") or claims.get("sub")
            if identity_hint:
                credential["identity_hint"] = identity_hint
            # end if
        # end if
        return credential
    # end def
# end class
