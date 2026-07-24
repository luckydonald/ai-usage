"""Browser cookie-capture login for the Claude private web API."""

import logging
from typing import Any

from curl_cffi.requests import AsyncSession

from ai_usage.providers.base import LoginMethod
from ai_usage.webview_login import capture_cookies_via_webview

LOGGER = logging.getLogger(__name__)

CLAUDE_LOGIN_URL = "https://claude.ai/login"


class CookieCaptureLogin(LoginMethod):
    key = "cookie_capture"
    display_name = "Sign in via browser"
    credential_kind = "cookie_jar"

    async def authenticate(self, options: dict[str, Any]) -> dict[str, Any] | None:
        del options
        # pywebview must run on the main thread (it raises WebViewException otherwise), so this
        # is a deliberate synchronous, blocking call rather than `asyncio.to_thread(...)`.
        cookies = capture_cookies_via_webview(CLAUDE_LOGIN_URL, self.display_name)
        return {"cookies": cookies} if cookies else None
    # end def

    async def discover_options(self, credential: dict[str, Any] | None) -> dict[str, Any]:
        cookies = (credential or {}).get("cookies") or {}
        if not cookies:
            LOGGER.warning("could not auto-detect Claude organization: no cookies were captured")
            return {}
        # end if
        try:
            # claude.ai sits behind Cloudflare (see CodexWebUsageProvider for the full story) —
            # impersonate a real Chrome TLS fingerprint so cf_clearance is honored.
            async with AsyncSession(
                timeout=20, cookies=cookies, base_url="https://claude.ai", impersonate="chrome",
            ) as client:
                response = await client.get("/api/organizations")
                response.raise_for_status()
                organizations = response.json()
            # end async with
        except Exception as exception:  # noqa: BLE001
            LOGGER.warning("could not auto-detect Claude organization: %s", exception)
            return {}
        # end try
        if not organizations:
            LOGGER.warning(
                "could not auto-detect Claude organization: /api/organizations returned no "
                "organizations for the captured cookies (%d cookie(s): %s)",
                len(cookies),
                ", ".join(sorted(cookies)),
            )
            return {}
        # end if
        if len(organizations) > 1:
            LOGGER.warning(
                "found %d Claude organizations, defaulting to the first (%s); pass --org-id "
                "explicitly to pick a different one (%s)",
                len(organizations),
                organizations[0].get("name"),
                ", ".join(f"{org.get('name')}={org.get('uuid')}" for org in organizations),
            )
        # end if
        return {"org_id": organizations[0]["uuid"]}
    # end def
# end class
