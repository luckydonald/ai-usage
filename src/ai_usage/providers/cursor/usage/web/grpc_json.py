"""Cursor gRPC-JSON fallback usage method (api2.cursor.sh, bearer-token authenticated)."""

import base64
import json
import logging
from datetime import UTC, datetime
from typing import Any

from curl_cffi.requests import AsyncSession

from ai_usage.models import AccountConfig, AccountIdentity, Metric, MinMaxUsage, ProviderFetchResult
from ai_usage.providers.base import ProviderError, UsageMethod
from ai_usage.providers.cursor._shared import COOKIE_NAME, extract_cursor_bearer_token
from ai_usage.providers.cursor.usage.web.private_api import (
    AUTH_ERROR_STATUS_CODES,
    cursor_cents_to_usd,
)

LOGGER = logging.getLogger(__name__)


def _decode_jwt_claims(token: str) -> dict[str, Any]:
    try:
        payload_segment = token.split(".")[1]
        padding = "=" * (-len(payload_segment) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_segment + padding))
    except Exception:  # noqa: BLE001
        return {}
    # end try
# end def


def parse_current_period_usage(payload: dict[str, Any], observed_at: datetime) -> list[Metric]:
    plan_usage = payload.get("planUsage") or {}
    metrics: list[Metric] = []
    if plan_usage:
        used = cursor_cents_to_usd(plan_usage.get("totalSpend"))
        limit = cursor_cents_to_usd(plan_usage.get("limit"))
        metrics.append(
            Metric(
                key="plan-usage",
                name="Plan usage",
                usage=MinMaxUsage(current=used, maximum=max(limit, used, 0.01), unit="USD"),
                observed_at=observed_at,
            )
        )
    # end if
    return metrics
# end def


class GrpcJsonUsage(UsageMethod):
    """Fallback Cursor usage leg: bearer-token api2.cursor.sh Connect/gRPC-JSON endpoints."""

    required_credential_kind = "cookie_jar"

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        cookies = (credential or {}).get("cookies") or {}
        token = extract_cursor_bearer_token(cookies)
        if not token:
            raise ProviderError("could not extract a Cursor access token from the session cookie")
        # end if
        observed = datetime.now(UTC)
        raw_payload: dict[str, Any] = {}
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        if cookies.get(COOKIE_NAME):
            headers["Cookie"] = f"{COOKIE_NAME}={cookies[COOKIE_NAME]}"
        # end if

        async with AsyncSession(
            timeout=20, base_url="https://api2.cursor.sh", impersonate="chrome", headers=headers,
        ) as client:
            usage_response = await client.post(
                "/aiserver.v1.DashboardService/GetCurrentPeriodUsage", data="{}"
            )
            if usage_response.status_code in AUTH_ERROR_STATUS_CODES:
                raise ProviderError("Cursor session is invalid or expired")
            # end if
            if usage_response.status_code != 200:
                raise ProviderError(
                    f"Cursor GetCurrentPeriodUsage returned HTTP {usage_response.status_code}"
                )
            # end if
            usage_payload = usage_response.json()
            raw_payload["current_period_usage"] = usage_payload

            try:
                plan_response = await client.post(
                    "/aiserver.v1.DashboardService/GetPlanInfo", data="{}"
                )
                if plan_response.status_code == 200:
                    raw_payload["plan_info"] = plan_response.json()
                # end if
            except Exception as exception:  # noqa: BLE001
                LOGGER.warning("could not fetch Cursor GetPlanInfo: %s", exception)
            # end try

            try:
                profile_response = await client.get("/auth/full_stripe_profile")
                if profile_response.status_code == 200:
                    raw_payload["stripe_profile"] = profile_response.json()
                # end if
            except Exception as exception:  # noqa: BLE001
                LOGGER.warning("could not fetch Cursor full_stripe_profile: %s", exception)
            # end try
        # end async with

        metrics = parse_current_period_usage(usage_payload, observed)
        if not metrics:
            raise ProviderError("Cursor GetCurrentPeriodUsage did not contain any usage windows")
        # end if

        claims = _decode_jwt_claims(token)
        identity = None
        if claims.get("email") or claims.get("sub"):
            identity = AccountIdentity(email=claims.get("email"), name=claims.get("sub"))
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
