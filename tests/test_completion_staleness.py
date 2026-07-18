import pytest

from ai_usage.cli import main
from ai_usage.completion_staleness import (
    HASH_VERSIONS,
    check_completion_staleness,
    hash_current_script,
    load_state,
    save_state,
)
from ai_usage.shell_completion import install_completion, installed_completion_hash
from tests.test_storage import temporary_paths


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """`install_completion()` writes to the real `~/.bashrc`/`~/.zshrc`/fish config by design —
    isolate `HOME` so these tests never touch the actual developer's shell startup files."""
    monkeypatch.setenv("HOME", str(tmp_path))
# end def


def test_every_currently_rendered_hash_is_in_the_version_registry() -> None:
    for shell in ("bash", "zsh", "fish"):
        current_hash = hash_current_script(main, shell)
        assert current_hash in HASH_VERSIONS, (
            f"{shell} completion script changed — add its new hash to HASH_VERSIONS "
            f"in completion_staleness.py (got {current_hash})"
        )
    # end for
# end def


def test_does_nothing_when_no_completion_is_installed(tmp_path, capsys) -> None:
    paths = temporary_paths(tmp_path)
    paths.ensure()

    check_completion_staleness(paths, main, interactive=True)

    assert capsys.readouterr().out == ""
# end def


def test_does_nothing_when_installed_completion_is_up_to_date(tmp_path, capsys) -> None:
    paths = temporary_paths(tmp_path)
    paths.ensure()
    install_completion(paths, main, "bash")

    check_completion_staleness(paths, main, interactive=True)

    assert capsys.readouterr().out == ""
# end def


def _install_stale_bash_completion(paths) -> None:
    install_completion(paths, main, "bash")
    script_path = paths.root / "completions" / "ai-usage.bash"
    script_path.write_text(
        "# ai-usage-completion-hash: " + "0" * 64 + "\nstale script\n", encoding="utf-8"
    )
# end def


def test_noninteractive_stale_logs_a_warning(tmp_path, caplog) -> None:
    paths = temporary_paths(tmp_path)
    paths.ensure()
    _install_stale_bash_completion(paths)

    with caplog.at_level("WARNING"):
        check_completion_staleness(paths, main, interactive=False)

    assert any("bash completion" in message for message in caplog.messages)
    assert installed_completion_hash(paths, "bash") == "0" * 64
# end def


def test_interactive_yes_updates_the_installed_script(tmp_path, monkeypatch) -> None:
    paths = temporary_paths(tmp_path)
    paths.ensure()
    _install_stale_bash_completion(paths)
    monkeypatch.setattr("ai_usage.completion_staleness.prompt_choice", lambda *a, **k: "y")

    check_completion_staleness(paths, main, interactive=True)

    assert installed_completion_hash(paths, "bash") == hash_current_script(main, "bash")
    assert load_state(paths).decision is None
# end def


def test_interactive_always_updates_and_persists_the_decision(tmp_path, monkeypatch) -> None:
    paths = temporary_paths(tmp_path)
    paths.ensure()
    _install_stale_bash_completion(paths)
    monkeypatch.setattr("ai_usage.completion_staleness.prompt_choice", lambda *a, **k: "a")

    check_completion_staleness(paths, main, interactive=True)

    assert installed_completion_hash(paths, "bash") == hash_current_script(main, "bash")
    assert load_state(paths).decision == "always"

    _install_stale_bash_completion(paths)
    check_completion_staleness(paths, main, interactive=False)
    assert installed_completion_hash(paths, "bash") == hash_current_script(main, "bash")
# end def


def test_interactive_skip_this_version_remembers_the_hash(tmp_path, monkeypatch) -> None:
    paths = temporary_paths(tmp_path)
    paths.ensure()
    _install_stale_bash_completion(paths)
    monkeypatch.setattr("ai_usage.completion_staleness.prompt_choice", lambda *a, **k: "s")

    check_completion_staleness(paths, main, interactive=True)

    assert installed_completion_hash(paths, "bash") == "0" * 64
    assert hash_current_script(main, "bash") in load_state(paths).acknowledged_hashes

    monkeypatch.setattr(
        "ai_usage.completion_staleness.prompt_choice",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not be asked again")),
    )
    check_completion_staleness(paths, main, interactive=True)
# end def


def test_interactive_never_persists_and_stops_checking(tmp_path, monkeypatch) -> None:
    paths = temporary_paths(tmp_path)
    paths.ensure()
    _install_stale_bash_completion(paths)
    monkeypatch.setattr("ai_usage.completion_staleness.prompt_choice", lambda *a, **k: "x")

    check_completion_staleness(paths, main, interactive=True)

    assert load_state(paths).decision == "never"
    assert installed_completion_hash(paths, "bash") == "0" * 64

    monkeypatch.setattr(
        "ai_usage.completion_staleness.prompt_choice",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not be asked again")),
    )
    check_completion_staleness(paths, main, interactive=True)
# end def


def test_state_round_trips(tmp_path) -> None:
    paths = temporary_paths(tmp_path)
    paths.ensure()
    state = load_state(paths)
    state.decision = "always"
    state.acknowledged_hashes.append("abc")

    save_state(paths, state)
    reloaded = load_state(paths)

    assert reloaded.decision == "always"
    assert reloaded.acknowledged_hashes == ["abc"]
# end def
