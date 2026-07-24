"""Non-interactive, screen-reader Claude usage collection (and CLI auth-status lookup)."""

import asyncio
import json
import logging
import re
import shlex
from datetime import UTC, datetime
from typing import Any

from ai_usage.models import AccountConfig, AccountIdentity, Metric, ProviderFetchResult, Usage
from ai_usage.providers.base import ProviderError, UsageMethod
from ai_usage.providers.claude._shared import claude_environment

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

ANSI_PATTERN = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
SECTION_PATTERN = re.compile(
    r"(?P<name>Current session|Current week \(all models\)|Current week \([^)]+\))"
    r".*?(?P<percentage>\d+(?:\.\d+)?)%\s+used.*?Resets\s+(?P<reset>[^\r\n]+)",
    re.IGNORECASE | re.DOTALL,
)
PROMO_PATTERN = re.compile(r"^\s*\+\d+%.*promo.*$", re.IGNORECASE | re.MULTILINE)


def normalize_claude_terminal_output(output: str) -> str:
    """Replace terminal controls with spacing so cursor-positioned words stay separate."""
    return ANSI_PATTERN.sub(" ", output).replace("\r", "")
# end def


def extract_claude_notes(output: str) -> list[str]:
    clean = normalize_claude_terminal_output(output)
    return [match.group(0).strip() for match in PROMO_PATTERN.finditer(clean)]
# end def


def claude_metric_key(name: str) -> str:
    normalized = name.casefold()
    if "session" in normalized:
        return "five-hours"
    elif "all models" in normalized:
        return "seven-days"
    # end if
    model = normalized.split("(", 1)[-1].rstrip(")")
    return "seven-days-" + re.sub(r"[^a-z0-9]+", "-", model).strip("-")
# end def


def claude_metric_model(name: str) -> str | None:
    """Extract the model name from a per-model section title, e.g. `Current week (Fable)` -> `Fable`."""
    normalized = name.casefold()
    if "session" in normalized or "all models" in normalized:
        return None
    # end if
    if "(" not in name or not name.endswith(")"):
        return None
    # end if
    return name.split("(", 1)[-1].rstrip(")").strip() or None
# end def


def parse_usage_output(output: str, observed_at: datetime) -> list[Metric]:
    clean = normalize_claude_terminal_output(output)
    metrics: list[Metric] = []
    for match in SECTION_PATTERN.finditer(clean):
        name = " ".join(match.group("name").split())
        metrics.append(
            Metric(
                key=claude_metric_key(name),
                name=name,
                usage=Usage(percentage=float(match.group("percentage"))),
                observed_at=observed_at,
                model=claude_metric_model(name),
                metadata={"reset_text": match.group("reset").strip()},
            )
        )
    # end for
    return metrics
# end def


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


async def run_claude_auth_status(command: str, profile_dir: str | None) -> AccountIdentity | None:
    """Run `claude auth status` (direct, non-interactive) and extract the account email."""
    command_parts = shlex.split(command)
    if not command_parts:
        return None
    # end if
    try:
        process = await asyncio.create_subprocess_exec(
            *command_parts,
            "auth",
            "status",
            env=claude_environment(profile_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exception:
        LOGGER.info("Claude auth status command could not start: %s", exception)
        return None
    # end try
    try:
        stdout, _stderr = await asyncio.wait_for(process.communicate(), timeout=15)
    except TimeoutError:
        process.kill()
        await process.wait()
        LOGGER.info("Claude auth status command timed out")
        return None
    # end try
    if process.returncode != 0:
        LOGGER.info("Claude auth status command exited with status %s", process.returncode)
        return None
    # end if
    try:
        payload = json.loads(stdout.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        LOGGER.info("Claude auth status command returned unparseable output")
        return None
    # end try
    email = payload.get("email")
    if not isinstance(email, str) or not email.strip():
        return None
    # end if
    return AccountIdentity(name=payload.get("orgName"), email=email)
# end def


class DirectCliUsage(UsageMethod):
    """Run Claude's `/usage` slash command non-interactively (screen-reader mode)."""

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
        output = await run_claude_usage_direct(command, profile_dir) or ""
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
