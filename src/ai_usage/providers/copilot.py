"""GitHub Copilot AI-credit billing provider."""

import calendar
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from ai_usage.icons import IconRef
from ai_usage.models import (
    AccountConfig,
    AccountIdentity,
    Metric,
    MinMaxUsage,
    ProviderFetchResult,
    Usage,
)
from ai_usage.providers.base import (
    ConfigurationField,
    DiscoveredAccount,
    Provider,
    ProviderError,
    canonical_login,
)


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
    icon = IconRef(set="brands", name="github")
    configuration_fields = (
        ConfigurationField(key="username", label="GitHub username", required=True),
        ConfigurationField(key="allowance", label="Monthly AI credits", kind="integer", required=True),
        ConfigurationField(key="billing_day", label="Billing cycle day", kind="integer", default=1),
        ConfigurationField(key="api_url", label="GitHub API URL", default="https://api.github.com"),
    )

    def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
        del result
        return canonical_login(account.options.get("username"), self.display_name)
    # end def

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


GITHUB_TOKEN_ENV_VARS = ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")


def copilot_cli_credentials(config_dir: Path) -> tuple[str | None, str | None]:
    """Reuse the Copilot CLI's own stored OAuth token, so no separate PAT is needed.

    Returns `(token, github_login)`; either element may be `None` when it can't be
    determined. Mirrors how community Copilot CLI status-line scripts resolve a token:
    environment variables first, then `~/.copilot/config.json`'s `copilot_tokens` map.
    """
    for env_var in GITHUB_TOKEN_ENV_VARS:
        if token := os.environ.get(env_var):
            return token, None
        # end if
    # end for
    config_path = config_dir / "config.json"
    if not config_path.exists():
        return None, None
    # end if
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None, None
    # end try
    tokens = config.get("copilot_tokens")
    tokens = tokens if isinstance(tokens, dict) else {}
    last_user = config.get("last_logged_in_user")
    last_user = last_user if isinstance(last_user, dict) else {}
    login = last_user.get("login") if isinstance(last_user.get("login"), str) else None
    host = last_user.get("host") if isinstance(last_user.get("host"), str) else None
    if login and host and (token := tokens.get(f"{host}:{login}")):
        return token, login
    # end if
    for token in tokens.values():
        if token:
            return token, login
        # end if
    # end for
    return None, login
# end def


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


class CopilotStatusProvider(Provider):
    service = "copilot"
    key = "statusline"
    display_name = "Copilot CLI quota (local session)"
    icon = IconRef(set="brands", name="github")
    configuration_fields = (
        ConfigurationField(key="config_dir", label="Copilot CLI config directory", kind="path"),
        ConfigurationField(key="billing_day", label="Billing cycle day", kind="integer", default=1),
        ConfigurationField(key="api_url", label="GitHub API URL", default="https://api.github.com"),
    )

    def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
        del account
        return canonical_login(
            result.identity.name if result.identity else None, self.display_name
        )
    # end def

    async def discover(self) -> list[DiscoveredAccount]:
        config_dir = Path.home() / ".copilot"
        if (config_dir / "config.json").exists():
            return [DiscoveredAccount(name="Copilot", options={"config_dir": str(config_dir)})]
        # end if
        return []
    # end def

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        del credential
        now = datetime.now(UTC)
        config_dir = (
            Path(str(account.options["config_dir"])).expanduser()
            if account.options.get("config_dir")
            else Path.home() / ".copilot"
        )
        token, login = copilot_cli_credentials(config_dir)
        if not token:
            raise ProviderError(
                "could not find a Copilot CLI access token in "
                f"{config_dir / 'config.json'} (or COPILOT_GITHUB_TOKEN/GH_TOKEN/GITHUB_TOKEN)"
            )
        # end if
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
