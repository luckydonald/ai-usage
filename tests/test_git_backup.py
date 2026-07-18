import subprocess
from datetime import UTC, datetime, timedelta

import pytest

from ai_usage.config import ConfigStore
from ai_usage.git_backup import maybe_run_git_backup
from tests.test_storage import temporary_paths


def _run(*args, cwd) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)
# end def


def _init_repo(root) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _run("git", "init", cwd=root)
    _run("git", "config", "user.email", "test@example.com", cwd=root)
    _run("git", "config", "user.name", "Test", cwd=root)
# end def


def test_backup_skipped_when_not_enabled(tmp_path) -> None:
    paths = temporary_paths(tmp_path)
    paths.ensure()
    _init_repo(paths.root)
    (paths.root / "history").mkdir(exist_ok=True)
    config = ConfigStore(paths)

    maybe_run_git_backup(paths, config, datetime.now(UTC))

    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=paths.root, capture_output=True, text=True
    )
    assert log.stdout.strip() == ""
# end def


def test_backup_commits_tracked_paths_when_enabled(tmp_path) -> None:
    paths = temporary_paths(tmp_path)
    paths.ensure()
    _init_repo(paths.root)
    (paths.root / "config.yml").write_text("git:\n  enabled: true\n", encoding="utf-8")
    (paths.root / "history").mkdir(exist_ok=True)
    (paths.root / "history" / "sample.jsonl").write_text("{}\n", encoding="utf-8")
    config = ConfigStore(paths)

    maybe_run_git_backup(paths, config, datetime.now(UTC))

    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=paths.root, capture_output=True, text=True
    )
    assert "Updated crawl results" in log.stdout
# end def


def test_backup_is_debounced(tmp_path) -> None:
    paths = temporary_paths(tmp_path)
    paths.ensure()
    _init_repo(paths.root)
    (paths.root / "config.yml").write_text("git:\n  enabled: true\n", encoding="utf-8")
    (paths.root / "history").mkdir(exist_ok=True)
    config = ConfigStore(paths)
    now = datetime.now(UTC)

    maybe_run_git_backup(paths, config, now)
    (paths.root / "history" / "second.jsonl").write_text("{}\n", encoding="utf-8")
    maybe_run_git_backup(paths, config, now + timedelta(seconds=1), debounce_seconds=600)

    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=paths.root, capture_output=True, text=True
    )
    assert len(log.stdout.strip().splitlines()) == 1
# end def


def test_backup_without_git_repo_does_not_raise(tmp_path) -> None:
    paths = temporary_paths(tmp_path)
    paths.ensure()
    (paths.root / "config.yml").write_text("git:\n  enabled: true\n", encoding="utf-8")
    config = ConfigStore(paths)

    maybe_run_git_backup(paths, config, datetime.now(UTC))
# end def
