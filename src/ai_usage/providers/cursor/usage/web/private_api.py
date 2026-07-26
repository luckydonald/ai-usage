"""Cursor private web API usage method (cursor.com/api/*, cookie-authenticated)."""

import logging
import urllib.parse
from datetime import UTC, datetime
from typing import Any

from curl_cffi.requests import AsyncSession

from ai_usage.models import (
    AccountConfig,
    AccountIdentity,
    Metric,
    MinMaxUsage,
    ProviderFetchResult,
)
from ai_usage.providers.base import ProviderError, UsageMethod
from ai_usage.providers.cursor._shared import COOKIE_NAME, extract_cursor_user_id

LOGGER = logging.getLogger(__name__)

AUTH_ERROR_STATUS_CODES = frozenset({401, 403})
JSON_HEADERS = {"Accept": "application/json"}


def cursor_cents_to_usd(value: Any) -> float:
    return round(float(value or 0) / 100.0, 2)
# end def


def parse_usage_summary(payload: dict[str, Any], observed_at: datetime) -> list[Metric]:
    individual = payload.get("individualUsage") or {}
    plan = individual.get("plan") or {}
    metrics: list[Metric] = []
    if plan:
        used = cursor_cents_to_usd(plan.get("used"))
        limit = cursor_cents_to_usd(plan.get("limit"))
        metrics.append(
            Metric(
                key="plan-usage",
                name="Plan usage",
                usage=MinMaxUsage(current=used, maximum=max(limit, used, 0.01), unit="USD"),
                observed_at=observed_at,
            )
        )
    # end if
    overall = individual.get("overall") or {}
    if overall.get("enabled"):
        used = cursor_cents_to_usd(overall.get("used"))
        limit = cursor_cents_to_usd(overall.get("limit"))
        metrics.append(
            Metric(
                key="overall-usage",
                name="Overall usage",
                usage=MinMaxUsage(current=used, maximum=max(limit, used, 0.01), unit="USD"),
                observed_at=observed_at,
            )
        )
    # end if
    return metrics
# end def


class PrivateApiUsage(UsageMethod):
    """Preferred Cursor usage leg: cookie-authenticated cursor.com/api/* JSON endpoints."""

    required_credential_kind = "cookie_jar"

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        cookies = (credential or {}).get("cookies") or {}
        if not cookies.get(COOKIE_NAME):
            raise ProviderError(f"Cursor session cookie ({COOKIE_NAME}) is missing")
        # end if
        observed = datetime.now(UTC)
        raw_payload: dict[str, Any] = {}
        async with AsyncSession(
            timeout=20, cookies=cookies, base_url="https://cursor.com", impersonate="chrome",
        ) as client:
            summary_response = await client.get("/api/usage-summary", headers=JSON_HEADERS)
            if summary_response.status_code in AUTH_ERROR_STATUS_CODES:
                raise ProviderError("Cursor session is invalid or expired")
            # end if
            if summary_response.status_code != 200:
                raise ProviderError(
                    f"Cursor /api/usage-summary returned HTTP {summary_response.status_code}"
                )
            # end if
            summary_payload = summary_response.json()
            raw_payload["usage_summary"] = summary_payload

            identity = None
            user_id = extract_cursor_user_id(cookies)
            try:
                me_response = await client.get("/api/auth/me", headers=JSON_HEADERS)
                if me_response.status_code == 200:
                    me_payload = me_response.json()
                    raw_payload["auth_me"] = me_payload
                    identity = AccountIdentity(
                        name=me_payload.get("name"), email=me_payload.get("email")
                    )
                    user_id = me_payload.get("sub") or user_id
                # end if
            except Exception as exception:  # noqa: BLE001
                LOGGER.warning("could not fetch Cursor /api/auth/me: %s", exception)
            # end try

            if user_id:
                try:
                    usage_response = await client.get(
                        "/api/usage", params={"user": urllib.parse.quote(user_id)},
                        headers={"Accept": "application/json"},
                    )
                    if usage_response.status_code == 200:
                        raw_payload["usage"] = usage_response.json()
                    # end if
                except Exception as exception:  # noqa: BLE001
                    LOGGER.warning("could not fetch Cursor /api/usage: %s", exception)
                # end try
            # end if
        # end async with

        metrics = parse_usage_summary(summary_payload, observed)
        if not metrics:
            raise ProviderError("Cursor usage-summary response did not contain any usage windows")
        # end if

        return ProviderFetchResult(
            service=account.service,
            provider=account.provider,
            account_id=account.id,
            fetched_at=observed,
            metrics=metrics,
            identity=identity,
            raw_payload=raw_payload,
        )
    # end def
# end class
