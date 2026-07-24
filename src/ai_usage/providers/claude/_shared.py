"""Shared configuration and diagnostics for Claude CLI collectors."""

import hashlib
import logging
import os
import re
import shlex
from pathlib import Path


LOGGER = logging.getLogger("ai_usage.providers.claude")
ANSI_PATTERN = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
SETUP_TEXT_STYLE_PATTERN = re.compile(r"Choose\s+the\s+text\s+style", re.IGNORECASE)
CLAUDE_ERROR_LOG_DIR = Path("/tmp/ai-usage/errors")


def claude_default_profile() -> Path:
    return Path.home() / ".claude"
# end def


def claude_profile_path(profile_dir: str | None) -> Path:
    return Path(profile_dir).expanduser() if profile_dir else claude_default_profile()
# end def


def canonical_claude_profile_dir(profile_dir: str | None) -> str | None:
    """Return an override only when the profile is not Claude's native default."""
    profile = claude_profile_path(profile_dir)
    if profile.resolve() == claude_default_profile().resolve():
        return None
    # end if
    return str(profile)
# end def


def claude_environment(profile_dir: str | None) -> dict[str, str]:
    environment = dict(os.environ)
    config_dir = canonical_claude_profile_dir(profile_dir)
    if config_dir:
        environment["CLAUDE_CONFIG_DIR"] = config_dir
    else:
        environment.pop("CLAUDE_CONFIG_DIR", None)
    # end if
    return environment
# end def


def claude_setup_required_message(
    output: str | None,
    command: str,
    profile_dir: str | None,
) -> str | None:
    """Explain how to complete Claude's first-run text-style selection."""
    clean = ANSI_PATTERN.sub(" ", output or "")
    if not SETUP_TEXT_STYLE_PATTERN.search(clean):
        return None
    # end if
    config_dir = canonical_claude_profile_dir(profile_dir)
    if config_dir:
        interactive_command = f"CLAUDE_CONFIG_DIR={shlex.quote(config_dir)} {shlex.quote(command)}"
        profile = config_dir
    else:
        profile = "the default Claude profile"
        interactive_command = shlex.quote(command)
    # end if
    return (
        f"Claude is waiting for first-run setup in {profile}; run "
        f"{interactive_command} interactively, choose a text style, then retry the crawl."
    )
# end def


def write_claude_error_log(output: str) -> Path:
    """Persist a failed Claude CLI transcript under a content-addressed temporary path."""
    digest = hashlib.sha256(output.encode("utf-8")).hexdigest()
    path = CLAUDE_ERROR_LOG_DIR / f"claude-cli.{digest}.log"
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not path.exists():
        temporary = path.with_suffix(".tmp")
        temporary.write_text(output, encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(path)
    # end if
    return path
# end def


def claude_cli_failure_message(output: str, command: str, profile_dir: str | None) -> str:
    """Persist Claude CLI failures and return the most actionable error message."""
    if output:
        error_log = write_claude_error_log(output)
        LOGGER.error("Saved Claude CLI transcript to %s", error_log)
    # end if
    setup_message = claude_setup_required_message(output, command, profile_dir)
    if setup_message:
        return setup_message
    # end if
    return "Claude /usage did not become ready; use Claude once to refresh the status relay"
# end def
