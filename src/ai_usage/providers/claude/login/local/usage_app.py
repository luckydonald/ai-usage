"""Discovery of a running ClaudeUsage.app local API (no credential is needed or stored)."""

import httpx

from ai_usage.providers.base import DiscoveredAccount, LoginMethod
from ai_usage.providers.claude.usage.local.usage_app import DEFAULT_BASE_URL


class UsageAppLogin(LoginMethod):
    key = "usage_app"
    display_name = "Local ClaudeUsage.app API"
    credential_kind = "none"

    async def discover(self) -> list[DiscoveredAccount]:
        try:
            async with httpx.AsyncClient(base_url=DEFAULT_BASE_URL, timeout=2) as client:
                response = await client.get("/health")
            healthy = response.status_code == 200 and response.json().get("ok") is True
        except (httpx.HTTPError, ValueError, AttributeError):
            return []
        # end try
        if not healthy:
            return []
        # end if
        return [DiscoveredAccount(name="ClaudeUsage.app", options={"base_url": DEFAULT_BASE_URL})]
    # end def
# end class
