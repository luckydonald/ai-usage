import subprocess
from datetime import UTC, datetime

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


def test_backup_commits_tracked_paths_when_enabled(tmp_path, caplog) -> None:
    paths = temporary_paths(tmp_path)
    paths.ensure()
    _init_repo(paths.root)
    (paths.root / "config.yml").write_text("git:\n  enabled: true\n", encoding="utf-8")
    (paths.root / "history").mkdir(exist_ok=True)
    (paths.root / "history" / "sample.jsonl").write_text("{}\n", encoding="utf-8")
    config = ConfigStore(paths)

    with caplog.at_level("INFO"):
        maybe_run_git_backup(paths, config, datetime.now(UTC))

    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=paths.root, capture_output=True, text=True
    )
    assert "Updated crawl results" in log.stdout
    assert any("Started committing git backup changes" in message for message in caplog.messages)
    assert any("Done committing git backup changes" in message for message in caplog.messages)
    # No remote is configured in this test repo, so the push attempt reports its failure.
    assert any("Git push failed" in message for message in caplog.messages)
# end def


def test_backup_logs_push_success_when_a_remote_accepts_it(tmp_path, caplog) -> None:
    paths = temporary_paths(tmp_path)
    paths.ensure()
    _init_repo(paths.root)
    remote = tmp_path / "remote.git"
    _run("git", "init", "--bare", str(remote), cwd=tmp_path)
    _run("git", "remote", "add", "origin", str(remote), cwd=paths.root)
    _run("git", "-C", str(paths.root), "config", "push.autoSetupRemote", "true", cwd=tmp_path)
    (paths.root / "config.yml").write_text("git:\n  enabled: true\n", encoding="utf-8")
    (paths.root / "history").mkdir(exist_ok=True)
    (paths.root / "history" / "sample.jsonl").write_text("{}\n", encoding="utf-8")
    config = ConfigStore(paths)

    with caplog.at_level("INFO"):
        maybe_run_git_backup(paths, config, datetime.now(UTC))

    assert any("Done pushing git backup changes" in message for message in caplog.messages)
    assert not any("Git push failed" in message for message in caplog.messages)
# end def


def test_backup_runs_after_every_fetch(tmp_path) -> None:
    paths = temporary_paths(tmp_path)
    paths.ensure()
    _init_repo(paths.root)
    (paths.root / "config.yml").write_text("git:\n  enabled: true\n", encoding="utf-8")
    (paths.root / "history").mkdir(exist_ok=True)
    config = ConfigStore(paths)
    now = datetime.now(UTC)

    maybe_run_git_backup(paths, config, now)
    (paths.root / "history" / "second.jsonl").write_text("{}\n", encoding="utf-8")
    maybe_run_git_backup(paths, config, now)

    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=paths.root, capture_output=True, text=True
    )
    assert len(log.stdout.strip().splitlines()) == 2
# end def


def test_backup_without_git_repo_does_not_raise(tmp_path) -> None:
    paths = temporary_paths(tmp_path)
    paths.ensure()
    (paths.root / "config.yml").write_text("git:\n  enabled: true\n", encoding="utf-8")
    config = ConfigStore(paths)

    maybe_run_git_backup(paths, config, datetime.now(UTC))
# end def
