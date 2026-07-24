"""Codex `/status` CLI (PTY-interactive) usage method."""

import asyncio
import re
from datetime import UTC, datetime
from typing import Any

from ai_usage.models import AccountConfig, FetchStatus, Metric, ProviderFetchResult, Usage
from ai_usage.providers.base import CredentialKind, ProviderError, UsageMethod
from ai_usage.providers.codex.usage.web.private_api import codex_model, extract_codex_notes

STATUS_PATTERN = re.compile(
    r"(?P<name>Weekly|\d+\s*hour)\s+limit:\s+.*?(?P<remaining>\d+(?:\.\d+)?)%\s+left\s+"
    r"\(resets\s+(?P<reset>[^)]+)\)",
    re.IGNORECASE,
)

STALE_WARNING_PATTERN = re.compile(r"limits may be stale", re.IGNORECASE)


def parse_codex_status(output: str, observed_at: datetime) -> list[Metric]:
    model = codex_model(output)
    metrics: list[Metric] = []
    for match in STATUS_PATTERN.finditer(output):
        name = match.group("name").lower().replace(" ", "-")
        key = "seven-days" if name == "weekly" else f"{name}s"
        remaining = float(match.group("remaining"))
        metrics.append(
            Metric(
                key=key,
                name=match.group("name"),
                usage=Usage(percentage=100 - remaining),
                observed_at=observed_at,
                model=model,
                metadata={"reset_text": match.group("reset")},
            )
        )
    # end for
    return metrics
# end def


async def run_codex_status(command: str) -> str:
    def run_terminal() -> str:
        import pexpect

        child = pexpect.spawn(command, encoding="utf-8", timeout=30)
        child.sendline("/status")
        child.expect("Weekly limit|hour limit", timeout=30)
        child.sendline("/status")
        child.expect("Weekly limit|hour limit", timeout=30)
        child.sendline("/quit")
        child.expect(pexpect.EOF, timeout=10)
        return child.before
    # end def

    return await asyncio.to_thread(run_terminal)
# end def


class StatusPtyUsage(UsageMethod):
    """Fetches Codex usage by driving the interactive Codex CLI's `/status` command."""

    required_credential_kind: CredentialKind = "none"

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        del credential
        observed = datetime.now(UTC)
        output = await run_codex_status(str(account.options.get("command", "codex")))
        metrics = parse_codex_status(output, observed)
        if not metrics:
            raise ProviderError("Codex /status output did not contain usage limits")
        # end if
        is_stale = STALE_WARNING_PATTERN.search(output) is not None
        return ProviderFetchResult(
            service="codex",
            provider="cli-status",
            account_id=account.id,
            fetched_at=observed,
            status=FetchStatus.STALE if is_stale else FetchStatus.SUCCESS,
            error="codex reported limits may be stale" if is_stale else None,
            metrics=metrics,
            notes=extract_codex_notes(output),
        )
    # end def
# end class
