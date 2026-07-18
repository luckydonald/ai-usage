"""Detects when an installed shell-completion script no longer matches the CLI's command tree.

Runs on (almost) every command via `cli.py`'s root callback. Never raises — a failed check
is logged and skipped, same philosophy as `git_backup.py`.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import click

from ai_usage.settings import Paths
from ai_usage.shell_completion import (
    hash_script,
    install_completion,
    installed_completion_hash,
    installed_completion_shells,
    render_script,
)

LOGGER = logging.getLogger(__name__)

# hash -> schema version, so messages can say "v2" instead of a raw hash — "less confusing to
# users" per the original ask. Whenever `render_script()`'s output changes for any shell, the
# new hash(es) must be added here (a unit test asserts every currently-rendered hash is present).
HASH_VERSIONS: dict[str, int] = {
    "47d43ae13c2472df292c0e2a57ed57e965d6d8c164167ad4d699c037d9eca6bf": 1,  # bash, v1
    "d82714ab44170e5ea39833e4667b346ca265cbb0916093d4e81e529ddb379352": 1,  # zsh, v1
    "c1d9ffb81e607b8660bafa1e2bf99c3f5b883f5fc766e14f639926951485e951": 1,  # fish, v1
}


@dataclass
class CompletionState:
    decision: str | None = None  # "always" | "never" | None
    acknowledged_hashes: list[str] = field(default_factory=list)
# end class


def _state_path(paths: Paths) -> Path:
    return paths.local / "completion_state.json"
# end def


def load_state(paths: Paths) -> CompletionState:
    path = _state_path(paths)
    if not path.exists():
        return CompletionState()
    # end if
    payload = json.loads(path.read_text(encoding="utf-8"))
    return CompletionState(
        decision=payload.get("decision"),
        acknowledged_hashes=list(payload.get("acknowledged_hashes", [])),
    )
# end def


def save_state(paths: Paths, state: CompletionState) -> None:
    path = _state_path(paths)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"decision": state.decision, "acknowledged_hashes": state.acknowledged_hashes}),
        encoding="utf-8",
    )
# end def


def version_label(script_hash: str) -> str:
    version = HASH_VERSIONS.get(script_hash)
    return f"v{version}" if version is not None else "an unrecognized version"
# end def


def prompt_choice(shell: str, installed_hash: str, current_hash: str) -> str:
    click.echo(
        f"The installed {shell} completion script ({version_label(installed_hash)}) is out of "
        f"date (latest is {version_label(current_hash)})."
    )
    click.echo("  y = yes, update now (this time)")
    click.echo("  a = yes, always update automatically from now on")
    click.echo("  n = no, not now (ask again next time)")
    click.echo("  s = no, skip this version (don't ask again for this version)")
    click.echo("  x = no, never ask again")
    return click.prompt(
        "Update completion now?",
        type=click.Choice(["y", "a", "n", "s", "x"]),
        default="y",
    )
# end def


def check_completion_staleness(
    paths: Paths, main: click.BaseCommand, interactive: bool
) -> None:
    # uvicorn's default logging config disables pre-existing loggers (disable_existing_loggers=True)
    # if `serve`/`up` ran earlier in this process — re-enable so our warning isn't silently dropped.
    LOGGER.disabled = False
    try:
        shells = installed_completion_shells(paths)
        if not shells:
            return
        # end if
        state = load_state(paths)
        if state.decision == "never":
            return
        # end if
        for shell in shells:
            installed_hash = installed_completion_hash(paths, shell)
            current_hash = hash_current_script(main, shell)
            if installed_hash is None or installed_hash == current_hash:
                continue
            # end if
            if current_hash in state.acknowledged_hashes:
                continue
            # end if
            if state.decision == "always":
                install_completion(paths, main, shell)
                continue
            # end if
            if not interactive:
                LOGGER.warning(
                    "%s completion is %s; latest is %s. Run `ai-usage completion --shell %s` "
                    "to update.",
                    shell,
                    version_label(installed_hash),
                    version_label(current_hash),
                    shell,
                )
                continue
            # end if
            choice = prompt_choice(shell, installed_hash, current_hash)
            if choice == "y":
                install_completion(paths, main, shell)
            elif choice == "a":
                state.decision = "always"
                save_state(paths, state)
                install_completion(paths, main, shell)
            elif choice == "s":
                state.acknowledged_hashes.append(current_hash)
                save_state(paths, state)
            elif choice == "x":
                state.decision = "never"
                save_state(paths, state)
            # end if ("n" falls through: ask again next time)
        # end for
    except OSError as exception:
        LOGGER.warning("shell completion staleness check failed: %s", exception)
    # end try
# end def


def hash_current_script(main: click.BaseCommand, shell: str) -> str:
    return hash_script(render_script(main, shell))
# end def
