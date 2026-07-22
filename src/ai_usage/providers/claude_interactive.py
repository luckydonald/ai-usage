"""Interactive pseudo-terminal fallback for Claude usage collection."""

import asyncio
import re
import time

from ai_usage.providers.base import ProviderError
from ai_usage.providers.claude_cli import claude_cli_failure_message, claude_environment


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
