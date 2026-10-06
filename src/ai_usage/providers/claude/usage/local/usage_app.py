"""Claude usage read from the ClaudeUsage.app macOS app's local HTTP API (no credential needed)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from ai_usage.models import AccountConfig, AccountIdentity, FetchStatus, Metric, ProviderFetchResult, Usage
from ai_usage.providers.base import ProviderError, UsageMethod
from ai_usage.providers.claude.usage.cli.direct import run_claude_auth_status

DEFAULT_BASE_URL = "http://127.0.0.1:47291"
STALE_AFTER = timedelta(minutes=10)
APP_HINT = "Is ClaudeUsage.app running with Settings → General → Local API enabled?"

WINDOWS: tuple[tuple[str, str, str, int, str | None], ...] = (
    # (endpoint, metric key, name, window seconds, model)
    ("session", "five-hours", "Five hours", 5 * 3600, None),
    ("weekly", "seven-days", "Seven days", 7 * 86400, None),
    ("opus", "seven-days-opus", "Current week (Opus)", 7 * 86400, "Opus"),
)


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    # end if
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    # end try
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
# end def


def parse_window(
    payload: dict[str, Any],
    key: str,
    name: str,
    seconds: int,
    model: str | None,
    observed_at: datetime,
) -> Metric:
    metadata = {"source": payload["source"]} if payload.get("source") else {}
    return Metric(
        key=key,
        name=name,
        usage=Usage(percentage=float(payload["percentUsed"])),
        observed_at=observed_at,
        reset_at=parse_timestamp(payload.get("resetsAt")),
        window_seconds=seconds,
        model=model,
        metadata=metadata,
    )
# end def


class UsageAppUsage(UsageMethod):
    required_credential_kind = "none"

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        del credential
        fetched_at = datetime.now(UTC)
        base_url = str(account.options.get("base_url") or DEFAULT_BASE_URL)
        payloads: dict[str, dict[str, Any]] = {}
        try:
            async with httpx.AsyncClient(base_url=base_url, timeout=10) as client:
                for endpoint, *_ in WINDOWS:
                    response = await client.get(f"/{endpoint}")
                    body = response.json() if response.content else {}
                    if response.status_code == 404 and body.get("error") == "window_unavailable":
                        # The plan simply has no such window: not an error, and never a fake 0%.
                        continue
                    # end if
                    if response.status_code == 503:
                        raise ProviderError(
                            "ClaudeUsage.app has no cached usage yet (just launched?); retry shortly"
                        )
                    # end if
                    if response.status_code != 200:
                        raise ProviderError(
                            f"ClaudeUsage.app returned HTTP {response.status_code} for /{endpoint}"
                        )
                    # end if
                    payloads[endpoint] = body
                # end for
        except httpx.TransportError as exception:
            raise ProviderError(f"Cannot reach ClaudeUsage.app at {base_url}. {APP_HINT}") from exception
        except ValueError as exception:
            raise ProviderError(f"ClaudeUsage.app at {base_url} returned invalid JSON") from exception
        # end try
        metrics: list[Metric] = []
        notes: list[str] = []
        for endpoint, key, name, seconds, model in WINDOWS:
            payload = payloads.get(endpoint)
            if payload is None:
                continue
            # end if
            observed_at = parse_timestamp(payload.get("lastUpdated")) or fetched_at
            if fetched_at - observed_at > STALE_AFTER:
                notes.append(
                    f"ClaudeUsage.app data for {name} is from {observed_at.isoformat()}; "
                    "the app may be backgrounded or signed out"
                )
            # end if
            try:
                metrics.append(parse_window(payload, key, name, seconds, model, observed_at))
            except (KeyError, TypeError, ValueError) as exception:
                raise ProviderError(f"ClaudeUsage.app /{endpoint} payload is malformed: {exception}") from exception
            # end try
        # end for
        if not metrics:
            raise ProviderError("ClaudeUsage.app reports no usage windows for this account")
        # end if
        return ProviderFetchResult(
            service=account.service,
            provider=account.provider,
            account_id=account.id,
            fetched_at=fetched_at,
            status=FetchStatus.SUCCESS,
            metrics=metrics,
            identity=await resolve_identity(account),
            raw_payload=payloads,
            notes=sorted(set(notes)),
        )
    # end def
# end class


async def resolve_identity(account: AccountConfig) -> AccountIdentity | None:
    """The app exposes no email, so use the configured one, else ask the Claude CLI."""
    email = account.options.get("email")
    if email:
        return AccountIdentity(email=str(email))
    # end if
    profile_dir = str(account.options["profile_dir"]) if account.options.get("profile_dir") else None
    return await run_claude_auth_status(str(account.options.get("command", "claude")), profile_dir)
# end def
