"""Kimi (Moonshot) usage method: api.kimi.com/coding/v1/usages."""

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

USAGES_URL = "https://api.kimi.com/coding/v1/usages"

MEMBERSHIP_DISPLAY_NAMES = {
    "LEVEL_INTERMEDIATE": "Kimi Code Intermediate",
    "LEVEL_ADVANCED": "Kimi Code Advanced",
    "LEVEL_PREMIUM": "Kimi Code Premium",
}


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
    # end if
# end def


def kimi_session_window(limits: list[dict[str, Any]]) -> dict[str, Any] | None:
    for entry in limits:
        window = entry.get("window") or {}
        if window.get("duration") == 300 and window.get("timeUnit") == "TIME_UNIT_MINUTE":
            return entry
        # end if
    # end for
    return limits[0] if limits else None
# end def


def kimi_membership_display_name(level: str | None) -> str | None:
    if not level:
        return None
    # end if
    if level in MEMBERSHIP_DISPLAY_NAMES:
        return MEMBERSHIP_DISPLAY_NAMES[level]
    # end if
    return "Kimi Code " + level.removeprefix("LEVEL_").replace("_", " ").title()
# end def


def parse_kimi_usages(payload: dict[str, Any], observed_at: datetime) -> list[Metric]:
    limits = payload.get("limits") or []
    entry = kimi_session_window(limits)
    if entry is None:
        return []
    # end if
    detail = entry.get("detail") or {}
    limit = _safe_float(detail.get("limit"))
    remaining = _safe_float(detail.get("remaining"))
    used = max(0.0, limit - remaining)
    reset_at = None
    reset_text = detail.get("resetTime")
    if isinstance(reset_text, str) and reset_text.strip():
        try:
            reset_at = datetime.fromisoformat(reset_text)
        except ValueError:
            reset_at = None
        # end try
    # end if
    return [
        Metric(
            key="session",
            name="Session usage",
            usage=MinMaxUsage(current=used, maximum=max(limit, used, 1.0), unit="requests"),
            observed_at=observed_at,
            reset_at=reset_at,
        )
    ]
# end def


class UsagesApiUsage(UsageMethod):
    required_credential_kind = "bearer_token"

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        token = (credential or {}).get("token")
        if not token:
            raise ProviderError("Kimi provider requires an OAuth access token")
        # end if
        observed = datetime.now(UTC)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=20, headers=headers) as client:
            response = await client.get(USAGES_URL)
        # end async with
        if response.status_code in (401, 403):
            raise ProviderError("Kimi session is invalid or expired")
        # end if
        if response.status_code != 200:
            raise ProviderError(f"Kimi /coding/v1/usages returned HTTP {response.status_code}")
        # end if
        payload = response.json()
        metrics = parse_kimi_usages(payload, observed)
        if not metrics:
            raise ProviderError("Kimi usages response did not contain any limit windows")
        # end if

        plan_name = kimi_membership_display_name(
            (payload.get("user") or {}).get("membership", {}).get("level")
        )

        return ProviderFetchResult(
            service=account.service,
            provider=account.provider,
            account_id=account.id,
            fetched_at=observed,
            metrics=metrics,
            subscription=SubscriptionStatus(plan_type=plan_name) if plan_name else None,
            raw_payload={"usages": payload},
        )
    # end def
# end class
