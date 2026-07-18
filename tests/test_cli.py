from pathlib import Path

import click
from click.testing import CliRunner

import ai_usage.api
from ai_usage.cli import credential_payload, main


def test_credential_payload_reads_file(tmp_path: Path) -> None:
    secret_file = tmp_path / "credential.json"
    secret_file.write_text('{"token":"secret"}', encoding="utf-8")

    assert credential_payload(None, secret_file) == '{"token":"secret"}'
# end def


def test_credential_payload_rejects_two_sources(tmp_path: Path) -> None:
    secret_file = tmp_path / "credential.json"
    secret_file.write_text("{}", encoding="utf-8")

    try:
        credential_payload("{}", secret_file)
    except click.UsageError as exception:
        assert "either" in str(exception)
    else:
        raise AssertionError("expected conflicting credential inputs to fail")
    # end try
# end def


def test_discovery_does_not_create_runtime_directory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    result = CliRunner().invoke(main, ["provider", "discover", "codex", "app-server"])

    assert result.exit_code == 0
    assert not (tmp_path / ".ai-usage").exists()
# end def


def test_run_all_passes_visible_progress_reporter(monkeypatch) -> None:
    async def run_server_and_crawler(paths, host, port, reporter, explicit_port=False) -> None:
        del paths, host, port, explicit_port
        reporter("Crawler started for 2 accounts: Claude, Codex.")
    # end def

    monkeypatch.setattr(ai_usage.api, "run_server_and_crawler", run_server_and_crawler)
    result = CliRunner().invoke(main, ["up"])

    assert result.exit_code == 0
    assert "Crawler started for 2 accounts: Claude, Codex." in result.output
# end def


def test_start_is_an_alias_for_up(monkeypatch) -> None:
    async def run_server_and_crawler(paths, host, port, reporter, explicit_port=False) -> None:
        del paths, host, port, explicit_port
        reporter("Crawler started for 2 accounts: Claude, Codex.")
    # end def

    monkeypatch.setattr(ai_usage.api, "run_server_and_crawler", run_server_and_crawler)
    result = CliRunner().invoke(main, ["start"])

    assert result.exit_code == 0
    assert "Crawler started for 2 accounts: Claude, Codex." in result.output
# end def


def test_bare_invocation_prints_status_and_help_without_starting_anything(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AI_USAGE_HOME", str(tmp_path))
    result = CliRunner().invoke(main, [])

    assert result.exit_code == 0
    assert "account(s) configured" in result.output
    assert "Last successful crawl:" in result.output
    assert "Usage:" in result.output
# end def
