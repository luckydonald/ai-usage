"""Claude usage read from the status-line relay file (falls through when missing or stale)."""

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_usage.models import AccountConfig, FetchStatus, Metric, ProviderFetchResult, Usage
from ai_usage.providers.base import ProviderError, UsageMethod
from ai_usage.providers.claude.usage.cli.direct import run_claude_auth_status


def parse_status_payload(payload: dict[str, Any], observed_at: datetime) -> list[Metric]:
    limits = payload.get("rate_limits") or {}
    metrics: list[Metric] = []
    for source_key, metric_key, name, seconds in (
        ("five_hour", "five-hours", "Five hours", 5 * 3600),
        ("seven_day", "seven-days", "Seven days", 7 * 86400),
    ):
        window = limits.get(source_key)
        if not window:
            continue
        # end if
        metrics.append(
            Metric(
                key=metric_key,
                name=name,
                usage=Usage(percentage=float(window["used_percentage"])),
                observed_at=observed_at,
                reset_at=datetime.fromtimestamp(int(window["resets_at"]), UTC),
                window_seconds=seconds,
            )
        )
    # end for
    return metrics
# end def


class RelayFileUsage(UsageMethod):
    required_credential_kind = "none"

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        del credential
        observed = datetime.now(UTC)
        relay_file_value = account.options.get("relay_file")
        if not relay_file_value:
            raise ProviderError("No Claude status relay file is configured")
        # end if
        relay_file = Path(str(relay_file_value)).expanduser()
        if not relay_file.exists():
            raise ProviderError(f"Claude status relay file {relay_file} does not exist")
        # end if
        stale_seconds = int(account.options.get("stale_seconds", 120))
        age = time.time() - relay_file.stat().st_mtime
        if age > stale_seconds:
            # Outdated numbers are worse than none: let the next method ask the CLI directly.
            raise ProviderError(f"Claude status relay file is {age:.0f}s old (limit {stale_seconds}s)")
        # end if
        payload = json.loads(relay_file.read_text(encoding="utf-8"))
        metrics = parse_status_payload(payload, observed)
        if not metrics:
            raise ProviderError("Claude status relay file did not contain rate limits")
        # end if
        command = str(account.options.get("command", "claude"))
        profile_dir = str(account.options["profile_dir"]) if account.options.get("profile_dir") else None
        identity = await run_claude_auth_status(command, profile_dir)
        return ProviderFetchResult(
            service=account.service,
            provider=account.provider,
            account_id=account.id,
            fetched_at=observed,
            status=FetchStatus.SUCCESS,
            metrics=metrics,
            identity=identity,
        )
    # end def
# end class
