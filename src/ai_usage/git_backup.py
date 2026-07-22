"""Optional git commit/push of the `~/.ai-usage` data directory after each fetch."""

import logging
import subprocess
from datetime import datetime

from ai_usage.config import ConfigStore
from ai_usage.progress import ProgressReporter
from ai_usage.settings import Paths

LOGGER = logging.getLogger("ai_usage.git_backup")

TRACKED_PATHS = (".gitignore", "history", "services")


def git_backup_enabled(config: ConfigStore) -> bool:
    return config.structured_global_config().git.enabled
# end def


def maybe_run_git_backup(
    paths: Paths,
    config: ConfigStore,
    now: datetime,
    reporter: ProgressReporter = LOGGER.info,
) -> None:
    """Commit (and push) the tracked data directories after a completed fetch.

    Never raises: a missing repo, a failed commit, or a failed push are all reported and skipped.
    """
    if not git_backup_enabled(config):
        return
    # end if
    if not (paths.root / ".git").is_dir():
        reporter(f"Git backup skipped: {paths.root} is not a git repository.")
        return
    # end if

    try:
        reporter("Started committing git backup changes.")
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
            reporter(f"Git commit failed: {commit.stderr.decode(errors='replace').strip()}")
            return
        # end if
        if commit.returncode == 1:
            reporter("Git backup has no changes to commit.")
            return
        # end if
        reporter(f"Done committing git backup changes in {paths.root}.")
        push = subprocess.run(["git", "-C", str(paths.root), "push"], capture_output=True)
        if push.returncode != 0:
            reporter(f"Git push failed: {push.stderr.decode(errors='replace').strip()}")
        else:
            reporter("Done pushing git backup changes.")
        # end if
    except OSError as exception:
        reporter(f"Git backup failed: {exception}")
    # end try
# end def
