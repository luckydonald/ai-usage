"""Experimental generic private-web usage adapter."""

from datetime import UTC, datetime
from typing import Any

import httpx

from ai_usage.models import AccountConfig, Metric, ProviderFetchResult, Usage
from ai_usage.providers.base import ConfigurationField, Provider, ProviderError


class PrivateWebProvider(Provider):
    experimental = True
    configuration_fields = (
        ConfigurationField(key="endpoint", label="Private usage endpoint", required=True),
        ConfigurationField(key="percentage_field", label="Percentage JSON field", required=True),
        ConfigurationField(key="metric_key", label="Metric key", default="usage"),
        ConfigurationField(key="metric_name", label="Metric name", default="Usage"),
    )

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


class CodexWebProvider(PrivateWebProvider):
    service = "codex"
    key = "web"
    display_name = "Codex private web API"
# end class


class ClaudeWebProvider(PrivateWebProvider):
    service = "claude"
    key = "web"
    display_name = "Claude private web API"
# end class


class CopilotEntitlementsProvider(PrivateWebProvider):
    service = "copilot"
    key = "entitlements"
    display_name = "Copilot private entitlement API"
# end class

