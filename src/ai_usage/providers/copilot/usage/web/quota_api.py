"""Copilot statusline usage method: `/copilot_internal/user` quota HTTP API."""

import re
from datetime import UTC, datetime
from typing import Any

import httpx

from ai_usage.models import (
    AccountConfig,
    AccountIdentity,
    Metric,
    MinMaxUsage,
    ProviderFetchResult,
    Usage,
)
from ai_usage.providers.base import ProviderError, UsageMethod
from ai_usage.providers.copilot.usage.web.billing_api import next_billing_reset


def copilot_quota_metric_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
# end def


def parse_copilot_quota_payload(
    payload: dict[str, Any], observed_at: datetime, reset_at: datetime
) -> list[Metric]:
    """Parse `GET /copilot_internal/user`'s `quota_snapshots` into per-feature metrics.

    Each snapshot (`premium_interactions`, `chat`, `completions`, ...) reports
    `percent_remaining` and, unless `unlimited`, an `entitlement` (monthly budget).
    """
    snapshots = payload.get("quota_snapshots")
    snapshots = snapshots if isinstance(snapshots, dict) else {}
    metrics: list[Metric] = []
    for name, snapshot in snapshots.items():
        if not isinstance(snapshot, dict) or snapshot.get("unlimited"):
            continue
        # end if
        percent_remaining = snapshot.get("percent_remaining")
        if not isinstance(percent_remaining, int | float):
            continue
        # end if
        used_percentage = round(100.0 - float(percent_remaining), 2)
        entitlement = snapshot.get("entitlement")
        remaining = snapshot.get("remaining")
        key = copilot_quota_metric_key(name)
        metric_name = name.replace("_", " ").title()
        if isinstance(entitlement, int | float) and entitlement > 0:
            current = (
                float(entitlement) - float(remaining)
                if isinstance(remaining, int | float)
                else float(entitlement) * used_percentage / 100.0
            )
            usage: Usage | MinMaxUsage = MinMaxUsage(
                current=round(current, 2), maximum=float(entitlement), unit="requests"
            )
        else:
            usage = Usage(percentage=used_percentage)
        # end if
        metrics.append(
            Metric(key=key, name=metric_name, usage=usage, observed_at=observed_at, reset_at=reset_at)
        )
    # end for
    return metrics
# end def


class QuotaApiUsage(UsageMethod):
    """`GET /copilot_internal/user` quota fetch.

    Note: the original `CopilotStatusProvider.fetch()` called `copilot_cli_credentials()`
    inline here to resolve a token from the local CLI config/env every fetch. That
    resolution now lives in `TokenReuseLogin` (a `LoginMethod`); this method only
    consumes an already-resolved `credential["token"]`.
    """

    service = "copilot"
    key = "statusline"
    required_credential_kind = "bearer_token"

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        token = (credential or {}).get("token")
        if not token:
            raise ProviderError(
                "could not find a Copilot CLI access token "
                "(via ~/.copilot/config.json or COPILOT_GITHUB_TOKEN/GH_TOKEN/GITHUB_TOKEN)"
            )
        # end if
        now = datetime.now(UTC)
        login = (credential or {}).get("login")
        api_url = str(account.options.get("api_url", "https://api.github.com")).rstrip("/")
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"{api_url}/copilot_internal/user",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
        # end async with
        if response.status_code != 200:
            raise ProviderError(f"Copilot internal quota API returned HTTP {response.status_code}")
        # end if
        payload: dict[str, Any] = response.json()
        reset = next_billing_reset(now, int(account.options.get("billing_day", 1)))
        metrics = parse_copilot_quota_payload(payload, now, reset)
        if not metrics:
            raise ProviderError("Copilot quota response did not contain any quota snapshots")
        # end if
        return ProviderFetchResult(
            service=self.service,
            provider=self.key,
            account_id=account.id,
            fetched_at=now,
            metrics=metrics,
            identity=AccountIdentity(name=login) if login else None,
            raw_payload=payload,
        )
    # end def
# end class
