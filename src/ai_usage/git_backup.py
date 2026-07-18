"""Optional, debounced git commit/push of the `~/.ai-usage` data directory."""

import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path

from ai_usage.config import ConfigStore
from ai_usage.settings import Paths

LOGGER = logging.getLogger("ai_usage.git_backup")

DEFAULT_DEBOUNCE_SECONDS = 600
TRACKED_PATHS = (".gitignore", "history", "services")


def git_backup_enabled(config: ConfigStore) -> bool:
    return config.structured_global_config().git.enabled
# end def


def _state_path(paths: Paths) -> Path:
    return paths.local / "git_backup_state.json"
# end def


def _last_attempt(paths: Paths) -> datetime | None:
    state_path = _state_path(paths)
    if not state_path.exists():
        return None
    # end if
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    return datetime.fromisoformat(payload["last_attempt"])
# end def


def _record_attempt(paths: Paths, now: datetime) -> None:
    _state_path(paths).write_text(json.dumps({"last_attempt": now.isoformat()}), encoding="utf-8")
# end def


def maybe_run_git_backup(
    paths: Paths,
    config: ConfigStore,
    now: datetime,
    debounce_seconds: int = DEFAULT_DEBOUNCE_SECONDS,
) -> None:
    """Commit (and push) the tracked data directories, at most once per `debounce_seconds`.

    Never raises: a missing repo, a failed commit, or a failed push are all logged and skipped —
    the next call (next debounce window) tries again.
    """
    # uvicorn's default logging config disables pre-existing loggers (disable_existing_loggers=True)
    # if `serve`/`up` ran earlier in this process — re-enable so our log lines aren't dropped.
    LOGGER.disabled = False
    if not git_backup_enabled(config):
        return
    # end if
    if not (paths.root / ".git").is_dir():
        LOGGER.warning("git backup is enabled but %s is not a git repository", paths.root)
        return
    # end if
    last_attempt = _last_attempt(paths)
    if last_attempt is not None and (now - last_attempt).total_seconds() < debounce_seconds:
        return
    # end if
    _record_attempt(paths, now)

    try:
        subprocess.run(
            ["git", "-C", str(paths.root), "add", *TRACKED_PATHS],
            check=True,
            capture_output=True,
        )
        commit = subprocess.run(
            [
                "git", "-C", str(paths.root), "commit",
                "-m", f"{now.strftime('%Y-%m-%d %H:%M:%S')}: Updated crawl results",
            ],
            capture_output=True,
        )
        if commit.returncode not in (0, 1):  # 1 == "nothing to commit", not an error here
            LOGGER.warning("git commit failed: %s", commit.stderr.decode(errors="replace"))
            return
        # end if
        if commit.returncode == 1:
            return
        # end if
        LOGGER.info("git backup: committed changes in %s.", paths.root)
        push = subprocess.run(["git", "-C", str(paths.root), "push"], capture_output=True)
        if push.returncode != 0:
            LOGGER.warning(
                "git push failed (will retry next cycle): %s", push.stderr.decode(errors="replace")
            )
        else:
            LOGGER.info("git backup: pushed successfully.")
        # end if
    except OSError as exception:
        LOGGER.warning("git backup failed: %s", exception)
    # end try
# end def
