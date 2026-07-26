"""Z.ai usage method: api.z.ai subscription + quota-limit JSON endpoints."""

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from ai_usage.models import (
    AccountConfig,
    Metric,
    MinMaxUsage,
    ProviderFetchResult,
    SubscriptionStatus,
)
from ai_usage.providers.base import ProviderError, UsageMethod

LOGGER = logging.getLogger(__name__)

BASE_URL = "https://api.z.ai"

# unit code -> granularity multiplier applied to `number` to get a period length in milliseconds.
UNIT_TO_MS = {
    1: 24 * 3600 * 1000,       # days
    3: 3600 * 1000,            # hours
    5: 60 * 1000,               # minutes
    6: 7 * 24 * 3600 * 1000,    # weeks
}

NO_PLAN_MARKERS = ("coding plan", "不存在")


def zai_period_ms(unit: int | None, number: int | None) -> int:
    multiplier = UNIT_TO_MS.get(unit or 0, 0)
    return multiplier * (number or 0)
# end def


def parse_zai_limits(payload: dict[str, Any], observed_at: datetime) -> list[Metric]:
    data = payload.get("data") or {}
    limits = data.get("limits") or []
    token_limits = [entry for entry in limits if entry.get("type") == "TOKENS_LIMIT"]
    time_limits = [entry for entry in limits if entry.get("type") == "TIME_LIMIT"]
    token_limits.sort(key=lambda entry: zai_period_ms(entry.get("unit"), entry.get("number")))

    metrics: list[Metric] = []
    for index, (metric_key, name) in enumerate((("session", "Session"), ("weekly", "Weekly"))):
        if index >= len(token_limits):
            continue
        # end if
        entry = token_limits[index]
        metrics.append(_build_metric(metric_key, name, entry, observed_at))
    # end for
    for entry in time_limits:
        metrics.append(_build_metric("web-search", "Web search", entry, observed_at))
    # end for
    return metrics
# end def


def _build_metric(
    metric_key: str, name: str, entry: dict[str, Any], observed_at: datetime
) -> Metric:
    current = entry.get("currentValue")
    number = entry.get("number") or 0
    remaining = entry.get("remaining")
    if current is None and remaining is not None:
        current = max(0, number - remaining)
    # end if
    current = float(current or 0)
    maximum = float(number) if number else max(current, 1.0)
    reset_ms = entry.get("nextResetTime")
    reset_at = None
    if isinstance(reset_ms, int | float) and reset_ms > 0:
        reset_at = datetime.fromtimestamp(reset_ms / 1000, tz=UTC)
    # end if
    return Metric(
        key=metric_key,
        name=name,
        usage=MinMaxUsage(current=current, maximum=maximum, unit="tokens"),
        observed_at=observed_at,
        reset_at=reset_at,
    )
# end def


class ZaiUsage(UsageMethod):
    required_credential_kind = "bearer_token"

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        token = (credential or {}).get("token")
        if not token:
            raise ProviderError("Z.ai provider requires an API key")
        # end if
        observed = datetime.now(UTC)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        raw_payload: dict[str, Any] = {}
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=20, headers=headers) as client:
            subscription_response = await client.get("/api/biz/subscription/list")
            if subscription_response.status_code in (401, 403):
                raise ProviderError("Z.ai API key is invalid or expired")
            # end if
            subscription_payload = subscription_response.json()
            raw_payload["subscription"] = subscription_payload
            message = str(subscription_payload.get("msg") or "").lower()
            if subscription_payload.get("success") is False and any(
                marker in message for marker in NO_PLAN_MARKERS
            ):
                raise ProviderError("Z.ai account has no active coding plan")
            # end if
            subscriptions = subscription_payload.get("data") or []
            subscription = None
            if subscriptions:
                first = subscriptions[0]
                subscription = SubscriptionStatus(
                    plan_type=first.get("productName"), status=first.get("status")
                )
            # end if

            quota_response = await client.get("/api/monitor/usage/quota/limit")
            if quota_response.status_code in (401, 403):
                raise ProviderError("Z.ai API key is invalid or expired")
            # end if
            quota_payload = quota_response.json()
            raw_payload["quota"] = quota_payload
        # end async with

        metrics = parse_zai_limits(quota_payload, observed)
        if not metrics:
            raise ProviderError("Z.ai quota response did not contain any usage limits")
        # end if

        return ProviderFetchResult(
            service=account.service,
            provider=account.provider,
            account_id=account.id,
            fetched_at=observed,
            metrics=metrics,
            subscription=subscription,
            raw_payload=raw_payload,
        )
    # end def
# end class
