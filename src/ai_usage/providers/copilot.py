"""GitHub Copilot AI-credit billing provider."""

import calendar
from datetime import UTC, datetime
from typing import Any

import httpx

from ai_usage.models import AccountConfig, Metric, MinMaxUsage, ProviderFetchResult
from ai_usage.providers.base import ConfigurationField, Provider, ProviderError


def next_billing_reset(now: datetime, day: int) -> datetime:
    year = now.year
    month = now.month
    candidate_day = min(day, calendar.monthrange(year, month)[1])
    candidate = datetime(year, month, candidate_day, tzinfo=UTC)
    if candidate <= now:
        month += 1
        if month == 13:
            month = 1
            year += 1
        # end if
        candidate_day = min(day, calendar.monthrange(year, month)[1])
        candidate = datetime(year, month, candidate_day, tzinfo=UTC)
    # end if
    return candidate
# end def


class CopilotBillingProvider(Provider):
    service = "copilot"
    key = "github-api"
    display_name = "GitHub AI-credit billing API"
    configuration_fields = (
        ConfigurationField(key="username", label="GitHub username", required=True),
        ConfigurationField(key="allowance", label="Monthly AI credits", kind="integer", required=True),
        ConfigurationField(key="billing_day", label="Billing cycle day", kind="integer", default=1),
        ConfigurationField(key="api_url", label="GitHub API URL", default="https://api.github.com"),
    )

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        token = (credential or {}).get("token")
        if not token:
            raise ProviderError("Copilot GitHub API provider requires an encrypted token")
        # end if
        now = datetime.now(UTC)
        username = str(account.options["username"])
        api_url = str(account.options.get("api_url", "https://api.github.com")).rstrip("/")
        url = f"{api_url}/users/{username}/settings/billing/ai_credit/usage"
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2026-03-10",
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(url, headers=headers, params={"year": now.year, "month": now.month})
        # end with
        if response.status_code != 200:
            raise ProviderError(f"GitHub billing API returned HTTP {response.status_code}")
        # end if
        payload: dict[str, Any] = response.json()
        current = sum(float(item.get("grossQuantity", 0)) for item in payload.get("usageItems", []))
        allowance = float(account.options["allowance"])
        reset = next_billing_reset(now, int(account.options.get("billing_day", 1)))
        return ProviderFetchResult(
            service=self.service,
            provider=self.key,
            account_id=account.id,
            fetched_at=now,
            metrics=[
                Metric(
                    key="monthly-ai-credits",
                    name="Monthly AI credits",
                    usage=MinMaxUsage(current=current, maximum=allowance, unit="AI credits"),
                    observed_at=now,
                    reset_at=reset,
                    metadata={"api_version": "2026-03-10"},
                )
            ],
        )
    # end def
# end class

