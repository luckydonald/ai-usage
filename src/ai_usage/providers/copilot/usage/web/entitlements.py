"""Generic private-web usage method (experimental), used by Copilot entitlements.

Placement note: `PrivateWebProvider` was written to be a generic, reusable base (its
`fetch()` has no Copilot-specific logic — cookie/header credential in, dotted-path JSON
percentage extraction out). The plan flagged an open question of whether this belongs in
`providers/base.py` instead of here. Kept in `copilot/usage/web/` for now: it currently
has exactly one consumer (`CopilotEntitlementsProvider`), and `providers/base.py` is
meant to hold the shared ABCs/errors/registry-facing contracts, not concrete
(even if generic) fetch implementations. If/when a second, non-Copilot provider wants
this same generic HTTP+dotted-path fetch, it should move to `base.py` (or a new
`providers/_shared/` module) at that point — no need to speculatively relocate it now.
"""

from datetime import UTC, datetime
from typing import Any

import httpx

from ai_usage.models import AccountConfig, Metric, ProviderFetchResult, Usage
from ai_usage.providers.base import ProviderError, UsageMethod


class GenericPrivateWebUsage(UsageMethod):
    """Experimental generic HTTP fetch with dotted-path JSON field extraction.

    `required_credential_kind` is `"cookie_jar"`: the credential this method consumes is
    a `{"cookies": {...}, "headers": {...}}` bundle (not a bare bearer token), matching
    what `fetch()` actually reads below.
    """

    required_credential_kind = "cookie_jar"

    def __init__(self, service: str, key: str) -> None:
        self.service = service
        self.key = key
    # end def

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        cookies = (credential or {}).get("cookies", {})
        headers = (credential or {}).get("headers", {})
        async with httpx.AsyncClient(timeout=20, cookies=cookies, headers=headers) as client:
            response = await client.get(str(account.options["endpoint"]))
        # end with
        if response.status_code != 200:
            raise ProviderError(f"private usage endpoint returned HTTP {response.status_code}")
        # end if
        payload: Any = response.json()
        for part in str(account.options["percentage_field"]).split("."):
            if not isinstance(payload, dict) or part not in payload:
                raise ProviderError(f"private usage schema no longer contains {part!r}")
            # end if
            payload = payload[part]
        # end for
        now = datetime.now(UTC)
        return ProviderFetchResult(
            service=self.service,
            provider=self.key,
            account_id=account.id,
            fetched_at=now,
            metrics=[
                Metric(
                    key=str(account.options.get("metric_key", "usage")),
                    name=str(account.options.get("metric_name", "Usage")),
                    usage=Usage(percentage=float(payload)),
                    observed_at=now,
                    metadata={"experimental": True},
                )
            ],
        )
    # end def
# end class
