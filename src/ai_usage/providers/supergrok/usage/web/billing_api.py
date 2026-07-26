"""SuperGrok (xAI) usage method: cli-chat-proxy.grok.com billing/settings JSON."""

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from ai_usage.models import (
    AccountConfig,
    AccountIdentity,
    Metric,
    MinMaxUsage,
    ProviderFetchResult,
    SubscriptionStatus,
)
from ai_usage.providers.base import ProviderError, UsageMethod

LOGGER = logging.getLogger(__name__)

BASE_URL = "https://cli-chat-proxy.grok.com/v1/"
TOKEN_AUTH_HEADER = "xai-grok-cli"
MAX_ATTEMPTS = 2


def unit_value(container: dict[str, Any], key: str) -> float | None:
    value = container.get(key)
    if isinstance(value, dict):
        value = value.get("val")
    # end if
    return float(value) if isinstance(value, int | float) else None
# end def


def extract_billing_config(payload: dict[str, Any]) -> dict[str, Any]:
    root = payload.get("billing", payload)
    return root.get("config") or {}
# end def


def is_grok_billing_timeout(status_code: int, payload: dict[str, Any]) -> bool:
    if status_code != 400:
        return False
    # end if
    code = str(payload.get("code") or "").lower()
    error = str(payload.get("error") or "").lower()
    return "operation was cancelled" in code and "timeout expired" in error
# end def


def parse_supergrok_billing(config: dict[str, Any], observed_at: datetime) -> list[Metric]:
    used = unit_value(config, "used")
    limit = unit_value(config, "monthlyLimit")
    percent = config.get("creditUsagePercent")
    if not isinstance(percent, int | float):
        product_usage = config.get("productUsage") or []
        percents = [entry.get("usagePercent") for entry in product_usage if isinstance(entry, dict)]
        percents = [value for value in percents if isinstance(value, int | float)]
        percent = max(percents) if percents else None
    # end if
    if used is None and limit is not None and isinstance(percent, int | float):
        used = limit * percent / 100.0
    # end if
    if used is None or limit is None:
        return []
    # end if
    return [
        Metric(
            key="credit-usage",
            name="Credit usage",
            usage=MinMaxUsage(current=used, maximum=max(limit, used, 0.01), unit="credits"),
            observed_at=observed_at,
        )
    ]
# end def


class BillingApiUsage(UsageMethod):
    required_credential_kind = "bearer_token"

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        credential = credential or {}
        token = credential.get("token")
        if not token:
            raise ProviderError("SuperGrok provider requires an OAuth access token")
        # end if
        observed = datetime.now(UTC)
        headers = {
            "Authorization": f"Bearer {token}",
            "X-XAI-Token-Auth": TOKEN_AUTH_HEADER,
            "Accept": "application/json",
            "User-Agent": "LLM Subscription Usage",
        }
        raw_payload: dict[str, Any] = {}
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=20, headers=headers) as client:
            billing_payload: dict[str, Any] | None = None
            for attempt in range(MAX_ATTEMPTS):
                response = await client.get("billing", params={"format": "credits"})
                if response.status_code in (401, 403):
                    raise ProviderError("SuperGrok session is invalid or expired")
                # end if
                body = response.json() if response.headers.get("content-type", "").startswith(
                    "application/json"
                ) else {}
                is_timeout = response.status_code == 400 and is_grok_billing_timeout(
                    response.status_code, body
                )
                if is_timeout:
                    if attempt + 1 < MAX_ATTEMPTS:
                        continue
                    # end if
                    raise ProviderError("SuperGrok billing endpoint timed out repeatedly")
                # end if
                if response.status_code != 200:
                    raise ProviderError(
                        f"SuperGrok billing endpoint returned HTTP {response.status_code}"
                    )
                # end if
                billing_payload = body
                break
            # end for
            raw_payload["billing"] = billing_payload

            plan_name = None
            try:
                settings_response = await client.get("settings")
                if settings_response.status_code == 200:
                    settings_payload = settings_response.json()
                    raw_payload["settings"] = settings_payload
                    plan_name = settings_payload.get("subscription_tier_display")
                # end if
            except httpx.HTTPError as exception:
                LOGGER.warning("could not fetch SuperGrok settings: %s", exception)
            # end try
        # end async with

        config = extract_billing_config(billing_payload or {})
        metrics = parse_supergrok_billing(config, observed)
        if not metrics:
            raise ProviderError("SuperGrok billing response did not contain any usage data")
        # end if

        identity = None
        if credential.get("identity_hint"):
            hint = credential["identity_hint"]
            identity = AccountIdentity(email=hint if "@" in hint else None, name=hint)
        # end if

        return ProviderFetchResult(
            service=account.service,
            provider=account.provider,
            account_id=account.id,
            fetched_at=observed,
            metrics=metrics,
            identity=identity,
            subscription=SubscriptionStatus(plan_type=plan_name) if plan_name else None,
            raw_payload=raw_payload,
        )
    # end def
# end class
