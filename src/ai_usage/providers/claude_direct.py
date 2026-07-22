"""Non-interactive, screen-reader Claude usage collection."""

import asyncio
import logging
import shlex

from ai_usage.providers.claude_cli import claude_environment


LOGGER = logging.getLogger("ai_usage.providers.claude")
DIRECT_USAGE_ARGS = (
    "--ax-screen-reader",
    "--name=/usage",
    "--no-chrome",
    "--print",
    "--no-session-persistence",
    "--safe-mode",
    "/usage",
)


async def run_claude_usage_direct(command: str, profile_dir: str | None) -> str | None:
    """Run `/usage` without a terminal UI, returning output only on clean completion."""
    command_parts = shlex.split(command)
    if not command_parts:
        return None
    # end if
    try:
        process = await asyncio.create_subprocess_exec(
            *command_parts,
            *DIRECT_USAGE_ARGS,
            env=claude_environment(profile_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exception:
        LOGGER.info("Claude screen-reader usage command could not start: %s", exception)
        return None
    # end try
    try:
        stdout, _stderr = await asyncio.wait_for(process.communicate(), timeout=30)
    except TimeoutError:
        process.kill()
        await process.wait()
        LOGGER.info("Claude screen-reader usage command timed out")
        return None
    # end try
    if process.returncode != 0:
        LOGGER.info("Claude screen-reader usage command exited with status %s", process.returncode)
        return None
    # end if
    output = stdout.decode("utf-8", errors="replace")
    return output if output.strip() else None
# end def
