"""Cline usage method: api.cline.bot balance/usages/plan-usage-limits, best-effort combine."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from ai_usage.models import AccountConfig, AccountIdentity, Metric, MinMaxUsage, ProviderFetchResult
from ai_usage.providers.base import ProviderError, UsageMethod

LOGGER = logging.getLogger(__name__)

BASE_URL = "https://api.cline.bot"
MICRO_DOLLAR = 1_000_000

PLAN_LIMIT_TYPES = {
    "five_hour": ("Five hours", 5 * 3600),
    "weekly": ("Weekly", 7 * 86400),
    "monthly": ("Monthly", 30 * 86400),
}


def cline_micro_dollars_to_usd(value: Any) -> float:
    return round(float(value or 0) / MICRO_DOLLAR, 2)
# end def


async def _get(client: httpx.AsyncClient, path: str) -> dict[str, Any] | None:
    try:
        response = await client.get(path)
    except httpx.HTTPError as exception:
        LOGGER.warning("Cline %s failed: %s", path, exception)
        return None
    # end try
    if response.status_code != 200:
        LOGGER.warning("Cline %s returned HTTP %s", path, response.status_code)
        return None
    # end if
    body = response.json()
    if body.get("success") is not True:
        LOGGER.warning("Cline %s returned success=false", path)
        return None
    # end if
    return body.get("data")
# end def


class ClineUsage(UsageMethod):
    required_credential_kind = "bearer_token"

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        token = (credential or {}).get("token")
        if not token:
            raise ProviderError("Cline provider requires an API key")
        # end if
        observed = datetime.now(UTC)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        raw_payload: dict[str, Any] = {}

        async with httpx.AsyncClient(base_url=BASE_URL, timeout=20, headers=headers) as client:
            me_response = await client.get("/api/v1/users/me")
            if me_response.status_code in (401, 403):
                raise ProviderError("Cline API key is invalid or expired")
            # end if
            if me_response.status_code == 429:
                raise ProviderError("Cline API rate limited")
            # end if
            if me_response.status_code != 200:
                raise ProviderError(f"Cline /users/me returned HTTP {me_response.status_code}")
            # end if
            me_body = me_response.json()
            if me_body.get("success") is not True:
                raise ProviderError("Cline /users/me did not return a usable account")
            # end if
            user_id = me_body.get("data", {}).get("id")
            if not user_id:
                raise ProviderError("Cline /users/me response did not include an account id")
            # end if
            raw_payload["me"] = me_body

            balance, usages, plan_limits = await asyncio.gather(
                _get(client, f"/api/v1/users/{user_id}/balance"),
                _get(client, f"/api/v1/users/{user_id}/usages"),
                _get(client, "/api/v1/users/me/plan/usage-limits"),
            )
        # end async with

        raw_payload["balance"] = balance
        raw_payload["usages"] = usages
        raw_payload["plan_limits"] = plan_limits

        metrics: list[Metric] = []
        if balance is not None:
            credits = cline_micro_dollars_to_usd(balance.get("balance"))
            metrics.append(
                Metric(
                    key="balance",
                    name="Credit balance",
                    usage=MinMaxUsage(current=credits, maximum=max(credits, 0.01), unit="USD"),
                    observed_at=observed,
                    metadata={"raw": "balance is a remaining-credits gauge, not a limit"},
                )
            )
        # end if
        if usages is not None:
            items = usages.get("items") or []
            total_tokens = sum(float(item.get("totalTokens") or 0) for item in items)
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
        if plan_limits is not None:
            for entry in plan_limits.get("limits") or []:
                type_key = entry.get("type")
                if type_key not in PLAN_LIMIT_TYPES:
                    continue
                # end if
                name, seconds = PLAN_LIMIT_TYPES[type_key]
                percent = max(0.0, min(100.0, float(entry.get("percentUsed") or 0)))
                reset_text = entry.get("resetsAt")
                reset_at = None
                if isinstance(reset_text, str) and reset_text.strip():
                    try:
                        reset_at = datetime.fromisoformat(reset_text)
                    except ValueError:
                        reset_at = None
                    # end try
                # end if
                metrics.append(
                    Metric(
                        key=f"clinepass-{type_key.replace('_', '-')}",
                        name=f"ClinePass {name}",
                        usage=MinMaxUsage(current=percent, maximum=100.0, unit="%"),
                        observed_at=observed,
                        reset_at=reset_at,
                        window_seconds=seconds,
                    )
                )
            # end for
        # end if

        if not metrics:
            raise ProviderError("Cline account has no balance, usage, or plan-limit data")
        # end if

        return ProviderFetchResult(
            service=account.service,
            provider=account.provider,
            account_id=account.id,
            fetched_at=observed,
            metrics=metrics,
            identity=AccountIdentity(name=str(user_id)),
            raw_payload=raw_payload,
        )
    # end def
# end class
