"""OpenRouter usage method: openrouter.ai credits + activity JSON endpoints."""

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from ai_usage.models import AccountConfig, Metric, MinMaxUsage, ProviderFetchResult
from ai_usage.providers.base import ProviderError, UsageMethod

LOGGER = logging.getLogger(__name__)

BASE_URL = "https://openrouter.ai"


class OpenRouterUsage(UsageMethod):
    required_credential_kind = "bearer_token"

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        token = (credential or {}).get("token")
        if not token:
            raise ProviderError("OpenRouter provider requires a provisioning key")
        # end if
        observed = datetime.now(UTC)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        raw_payload: dict[str, Any] = {}

        async with httpx.AsyncClient(base_url=BASE_URL, timeout=20, headers=headers) as client:
            credits_response = await client.get("/api/v1/credits")
            if credits_response.status_code == 401:
                raise ProviderError("OpenRouter provisioning key is invalid or expired")
            # end if
            if credits_response.status_code == 429:
                raise ProviderError("OpenRouter API rate limited")
            # end if
            if credits_response.status_code != 200:
                raise ProviderError(
                    f"OpenRouter /api/v1/credits returned HTTP {credits_response.status_code} — "
                    "note only Provisioning Keys (not regular API keys) can call this endpoint"
                )
            # end if
            credits_payload = credits_response.json()
            raw_payload["credits"] = credits_payload

            try:
                activity_response = await client.get("/api/v1/activity")
                activity_payload = (
                    activity_response.json() if activity_response.status_code == 200 else None
                )
            except httpx.HTTPError as exception:
                LOGGER.warning("OpenRouter /api/v1/activity failed: %s", exception)
                activity_payload = None
            # end try
        # end async with

        data = credits_payload.get("data") or {}
        total_credits = float(data.get("total_credits") or 0)
        used = float(data.get("total_usage") or 0)
        metrics = [
            Metric(
                key="credits",
                name="Credits used",
                usage=MinMaxUsage(current=used, maximum=max(total_credits, used, 0.01), unit="USD"),
                observed_at=observed,
            )
        ]

        if activity_payload is not None:
            raw_payload["activity"] = activity_payload
            entries = activity_payload.get("data") or []
            total_tokens = sum(
                float(entry.get("prompt_tokens") or 0) + float(entry.get("completion_tokens") or 0)
                for entry in entries
            )
            metrics.append(
                Metric(
                    key="tokens-used",
                    name="Tokens used",
                    usage=MinMaxUsage(
                        current=total_tokens, maximum=max(total_tokens, 1.0), unit="tokens"
                    ),
                    observed_at=observed,
                )
            )
        # end if

        return ProviderFetchResult(
            service=account.service,
            provider=account.provider,
            account_id=account.id,
            fetched_at=observed,
            metrics=metrics,
            raw_payload=raw_payload,
        )
    # end def
# end class
