"""MiniMax usage method: region-fallback coding_plan/remains JSON endpoints."""

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from ai_usage.models import AccountConfig, Metric, MinMaxUsage, ProviderFetchResult
from ai_usage.providers.base import ProviderError, UsageMethod

LOGGER = logging.getLogger(__name__)

REGION_ENDPOINTS: dict[str, tuple[str, ...]] = {
    "global": (
        "https://api.minimax.io/v1/api/openplatform/coding_plan/remains",
        "https://api.minimax.io/v1/coding_plan/remains",
        "https://www.minimax.io/v1/api/openplatform/coding_plan/remains",
    ),
    "cn": (
        "https://api.minimaxi.com/v1/api/openplatform/coding_plan/remains",
        "https://api.minimaxi.com/v1/coding_plan/remains",
    ),
}

# priority-ordered candidate field names for "used"/"remaining"/"remains" counts.
USED_FIELD_CANDIDATES = (
    "current_interval_usage_count",
    "current_interval_remaining_count",
    "current_interval_remains_count",
)


def minimax_normalize_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, int | float) or value <= 0:
        return None
    # end if
    seconds = value if value < 10_000_000_000 else value / 1000
    return datetime.fromtimestamp(seconds, tz=UTC)
# end def


def minimax_pick_used(entry: dict[str, Any]) -> tuple[float, float]:
    """Returns `(used, total)`, resolving used/remaining via a field-name priority chain."""
    total = float(entry.get("current_interval_total_count") or 0)
    for field in USED_FIELD_CANDIDATES:
        value = entry.get(field)
        if value is None:
            continue
        # end if
        if field == "current_interval_usage_count":
            return float(value), total or float(value)
        # end if
        # remaining/remains-style fields: used = total - remaining
        remaining = float(value)
        return max(0.0, total - remaining), total or remaining
    # end for
    return 0.0, total or 1.0
# end def


def parse_minimax_remains(payload: dict[str, Any], observed_at: datetime) -> list[Metric]:
    metrics: list[Metric] = []
    for entry in payload.get("model_remains") or []:
        used, total = minimax_pick_used(entry)
        plan_name = (
            entry.get("plan_name")
            or entry.get("current_subscribe_title")
            or entry.get("plan")
            or "plan"
        )
        slug = "".join(char if char.isalnum() else "-" for char in str(plan_name).lower())
        key = slug.strip("-") or "plan"
        metrics.append(
            Metric(
                key=key,
                name=str(plan_name),
                usage=MinMaxUsage(current=used, maximum=max(total, used, 1.0), unit="requests"),
                observed_at=observed_at,
                reset_at=minimax_normalize_timestamp(entry.get("end_time")),
            )
        )
    # end for
    return metrics
# end def


class MiniMaxUsage(UsageMethod):
    required_credential_kind = "bearer_token"

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        token = (credential or {}).get("token")
        if not token:
            raise ProviderError("MiniMax provider requires an API key")
        # end if
        region = str(account.options.get("region") or "global").strip().lower()
        endpoints = REGION_ENDPOINTS.get(region, REGION_ENDPOINTS["global"])
        observed = datetime.now(UTC)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        payload: dict[str, Any] | None = None
        async with httpx.AsyncClient(timeout=20, headers=headers) as client:
            for url in endpoints:
                response = await client.get(url)
                if response.status_code in (401, 403):
                    raise ProviderError("MiniMax API key is invalid or expired")
                # end if
                if response.status_code != 200:
                    continue
                # end if
                candidate = response.json()
                base_resp = candidate.get("base_resp") or {}
                if base_resp.get("status_code") != 0:
                    continue
                # end if
                payload = candidate
                break
            # end for
        # end async with
        if payload is None:
            raise ProviderError(
                f"MiniMax coding-plan endpoint unavailable in all fallback URLs for region "
                f"{region!r}"
            )
        # end if

        metrics = parse_minimax_remains(payload, observed)
        if not metrics:
            raise ProviderError("MiniMax response did not contain any plan usage")
        # end if

        return ProviderFetchResult(
            service=account.service,
            provider=account.provider,
            account_id=account.id,
            fetched_at=observed,
            metrics=metrics,
            raw_payload={"model_remains": payload},
        )
    # end def
# end class
