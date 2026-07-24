"""Interactive pseudo-terminal fallback for Claude usage collection."""

import asyncio
import re
import time
from datetime import UTC, datetime
from typing import Any

from ai_usage.models import AccountConfig, ProviderFetchResult
from ai_usage.providers.base import ProviderError, UsageMethod
from ai_usage.providers.claude._shared import claude_cli_failure_message, claude_environment
from ai_usage.providers.claude.usage.cli.direct import (
    extract_claude_notes,
    parse_usage_output,
    run_claude_auth_status,
)

RAW_SETUP_TEXT_STYLE_PATTERN = re.compile(r"Choose.*?the.*?text.*?style", re.IGNORECASE)


async def run_claude_usage(command: str, profile_dir: str | None) -> str:
    """Collect `/usage` through Claude's interactive terminal when direct mode fails."""
    def run_terminal() -> str:
        import pexpect

        child = pexpect.spawn(
            command,
            encoding="utf-8",
            timeout=30,
            env=claude_environment(profile_dir),
        )
        try:
            startup_state = child.expect([RAW_SETUP_TEXT_STYLE_PATTERN, "❯"], timeout=30)
            startup_output = child.before + child.after
            if startup_state == 0:
                raise ProviderError(claude_cli_failure_message(startup_output, command, profile_dir))
            # end if
            child.sendline("/usage")
            child.expect("Current", timeout=30)
            usage_output = child.before + child.after
            child.expect("session", timeout=30)
            usage_output += child.before + child.after
            time.sleep(1)
            child.sendline("/exit")
            child.expect(pexpect.EOF, timeout=10)
            return usage_output + child.before
        except (pexpect.TIMEOUT, pexpect.EOF) as exception:
            raise ProviderError(
                claude_cli_failure_message(child.before or "", command, profile_dir)
            ) from exception
        finally:
            if child.isalive():
                child.close(force=True)
            # end if
        # end try
    # end def

    return await asyncio.to_thread(run_terminal)
# end def


class InteractiveCliUsage(UsageMethod):
    """Run Claude's `/usage` slash command through an interactive PTY session."""

    required_credential_kind = "none"

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        del credential
        observed = datetime.now(UTC)
        command = str(account.options.get("command", "claude"))
        profile_dir = str(account.options["profile_dir"]) if account.options.get("profile_dir") else None
        identity = await run_claude_auth_status(command, profile_dir)
        output = await run_claude_usage(command, profile_dir)
        metrics = parse_usage_output(output, observed)
        if not metrics:
            raise ProviderError("Claude /usage output did not contain recognized usage sections")
        # end if
        return ProviderFetchResult(
            service=account.service,
            provider=account.provider,
            account_id=account.id,
            fetched_at=observed,
            metrics=metrics,
            notes=extract_claude_notes(output),
            identity=identity,
        )
    # end def
# end class
