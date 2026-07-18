import asyncio
import base64
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from click.testing import CliRunner
from sqlalchemy import func, select

import ai_usage.cli
from ai_usage.cli import Runtime, create_account, main, select_discovered_account
from ai_usage.config import ConfigStore
from ai_usage.database import Database
from ai_usage.history import HistoryStore
from ai_usage.models import AccountConfig, Metric, ProviderFetchResult, Usage
from ai_usage.orm import CredentialRecord, CrawlStateRecord, FetchRunRecord
from ai_usage.provider_discovery import DiscoveryChoice
from ai_usage.provider_tui import SelectionChoice
from ai_usage.providers import built_in_registry
from ai_usage.providers.base import DiscoveredAccount
from ai_usage.settings import Paths


def configured_paths(tmp_path: Path, monkeypatch) -> Paths:
    monkeypatch.setenv("AI_USAGE_HOME", str(tmp_path / "ai-usage"))
    monkeypatch.setenv(
        "AI_USAGE_CREDENTIAL_KEY",
        base64.urlsafe_b64encode(os.urandom(32)).decode(),
    )
    return Paths.from_environment()
# end def


def test_provider_group_exposes_aliases_and_removes_flat_commands() -> None:
    runner = CliRunner()
    root_help = runner.invoke(main, ["--help"])
    provider_help = runner.invoke(main, ["provider", "--help"])

    assert root_help.exit_code == 0
    assert "  provider " in root_help.output
    assert "  add " not in root_help.output
    assert "  discover " not in root_help.output
    assert "  providers " not in root_help.output
    for command in ("add", "new", "list", "ls", "remove", "del", "rm", "status", "info"):
        assert f"  {command}" in provider_help.output
    # end for
# end def


def test_no_input_add_lists_choices_without_creating_runtime(tmp_path: Path, monkeypatch) -> None:
    paths = configured_paths(tmp_path, monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))

    result = CliRunner().invoke(main, ["provider", "add", "--no-input"])

    assert result.exit_code == 0
    assert "No local accounts discovered" in result.output
    assert "Manual provider adapters:" in result.output
    assert "codex/app-server" in result.output
    assert not paths.root.exists()
# end def


def test_list_and_ls_show_active_and_removed_accounts(tmp_path: Path, monkeypatch) -> None:
    paths = configured_paths(tmp_path, monkeypatch)
    paths.ensure()
    config = ConfigStore(paths)
    active = config.create_account("codex", "app-server", "Personal", None, {})
    removed = config.create_account("claude", "statusline", "Old work", None, {})
    config.save_account(
        removed.model_copy(update={"enabled": False, "removed_at": datetime.now(UTC)})
    )

    listed = CliRunner().invoke(main, ["provider", "list"])
    aliased = CliRunner().invoke(main, ["provider", "ls", "codex"])

    assert listed.exit_code == 0
    assert active.id in listed.output
    assert removed.id in listed.output
    assert "removed" in listed.output
    assert aliased.exit_code == 0
    assert active.id in aliased.output
    assert removed.id not in aliased.output
# end def


def test_new_alias_manually_configures_provider(tmp_path: Path, monkeypatch) -> None:
    paths = configured_paths(tmp_path, monkeypatch)
    secret_file = tmp_path / "github.json"
    secret_file.write_text('{"token":"github-secret"}', encoding="utf-8")

    result = CliRunner().invoke(
        main,
        [
            "provider",
            "new",
            "copilot",
            "github-api",
            "--name",
            "Work Copilot",
            "--secret-file",
            str(secret_file),
            "--username",
            "lucy",
            "--allowance",
            "300",
            "--no-input",
        ],
    )

    assert result.exit_code == 0
    assert "Added Work Copilot" in result.output
    account = ConfigStore(paths).list_accounts()[0]
    assert account.options["username"] == "lucy"
    assert account.options["allowance"] == 300

    async def credential() -> dict[str, str]:
        database = Database(paths)
        assert account.credential_id is not None
        value = await database.get_credential(account.credential_id)
        await database.close()
        return value
    # end def

    assert asyncio.run(credential()) == {"token": "github-secret"}
# end def


def test_discovered_account_is_restored_with_same_identity(tmp_path: Path, monkeypatch) -> None:
    paths = configured_paths(tmp_path, monkeypatch)

    async def exercise() -> tuple[str, str, str]:
        runtime = Runtime(paths)
        await runtime.initialize()
        discovered = DiscoveryChoice(
            service="codex",
            provider="app-server",
            provider_name="Codex app-server",
            account=DiscoveredAccount(name="Codex", options={"profile_dir": "/profiles/codex"}),
        )
        first, first_action = await create_account(
            runtime, "codex", "app-server", None, None, True, {}, discovered
        )
        runtime.config.save_account(
            first.model_copy(update={"enabled": False, "removed_at": datetime.now(UTC)})
        )
        restored, restored_action = await create_account(
            runtime, "codex", "app-server", None, None, True, {}, discovered
        )
        existing, existing_action = await create_account(
            runtime, "codex", "app-server", None, None, True, {}, discovered
        )
        await runtime.close()
        assert first.id == restored.id == existing.id
        assert restored.removed_at is None
        return first_action, restored_action, existing_action
    # end def

    assert asyncio.run(exercise()) == ("added", "restored", "existing")
# end def


def test_discovered_credentials_are_encrypted(tmp_path: Path, monkeypatch) -> None:
    paths = configured_paths(tmp_path, monkeypatch)

    async def exercise() -> None:
        runtime = Runtime(paths)
        await runtime.initialize()
        discovered = DiscoveryChoice(
            service="codex",
            provider="app-server",
            provider_name="Codex app-server",
            account=DiscoveredAccount(
                name="Imported Codex",
                options={"profile_dir": "/profiles/imported"},
                credential={"token": "discovered-secret"},
            ),
        )
        account, action = await create_account(
            runtime,
            "codex",
            "app-server",
            None,
            discovered.account.credential,
            True,
            {},
            discovered,
        )
        assert action == "added"
        assert account.credential_id is not None
        assert await runtime.database.get_credential(account.credential_id) == {
            "token": "discovered-secret"
        }
        await runtime.close()
        assert b"discovered-secret" not in paths.database.read_bytes()
    # end def

    asyncio.run(exercise())
# end def


def test_manual_configuration_is_a_separate_selection(tmp_path: Path, monkeypatch) -> None:
    paths = configured_paths(tmp_path, monkeypatch)
    runtime = Runtime(paths)
    runtime.providers = built_in_registry()
    titles: list[str] = []

    async def choose(title: str, choices: list[SelectionChoice]) -> str:
        titles.append(title)
        assert choices
        if len(titles) == 1:
            return "manual"
        # end if
        return next(choice.key for choice in choices if choice.label == "copilot/github-api")
    # end def

    monkeypatch.setattr(ai_usage.cli, "select_choice", choose)
    selected, manual = asyncio.run(select_discovered_account(runtime, "copilot", None))
    asyncio.run(runtime.close())

    assert selected is None
    assert manual == ("copilot", "github-api")
    assert titles == ["Choose an account to add", "Choose a provider adapter"]
# end def


def test_status_and_two_stage_removal(tmp_path: Path, monkeypatch) -> None:
    paths = configured_paths(tmp_path, monkeypatch)

    async def prepare() -> AccountConfig:
        paths.ensure()
        database = Database(paths)
        await database.migrate()
        credential_id = await database.put_credential("codex", "Personal", {"token": "secret"})
        config = ConfigStore(paths)
        account = config.create_account(
            "codex", "app-server", "Personal", credential_id, {"profile_dir": "/profiles/codex"}
        )
        now = datetime.now(UTC)
        await HistoryStore(paths, database).append_result(
            ProviderFetchResult(
                service=account.service,
                provider=account.provider,
                account_id=account.id,
                fetched_at=now,
                metrics=[
                    Metric(
                        key="five-hours",
                        name="Five hours",
                        usage=Usage(percentage=42),
                        observed_at=now,
                    )
                ],
            )
        )
        async with database.sessions() as session:
            session.add(
                FetchRunRecord(
                    id="fetch-run",
                    account_id=account.id,
                    provider=account.provider,
                    started_at=now,
                    finished_at=now,
                    success=True,
                )
            )
            session.add(
                CrawlStateRecord(
                    account_id=account.id,
                    next_run_at=now + timedelta(minutes=10),
                )
            )
            await session.commit()
        # end with
        await database.close()
        return account
    # end def

    account = asyncio.run(prepare())
    runner = CliRunner()
    status = runner.invoke(main, ["provider", "info", "--account", account.id])
    removed = runner.invoke(
        main, ["provider", "remove", "--account", account.id, "--no-input"]
    )
    removed_again = runner.invoke(
        main, ["provider", "rm", "--account", account.id, "--no-input"]
    )

    assert status.exit_code == 0
    assert "Five hours: 42.0%" in status.output
    assert "Last fetch: succeeded" in status.output
    assert "Next crawl:" in status.output
    assert removed.exit_code == 0
    assert "historical usage was preserved" in removed.output
    assert removed_again.exit_code == 0
    tombstone = ConfigStore(paths).get_account(account.id)
    assert tombstone.enabled is False
    assert tombstone.removed_at is not None
    assert tombstone.credential_id is None
    assert paths.history.joinpath("v1", account.service, account.id).exists()

    async def local_state_counts() -> tuple[int, int, int]:
        database = Database(paths)
        async with database.sessions() as session:
            credentials = await session.scalar(select(func.count()).select_from(CredentialRecord))
            fetch_runs = await session.scalar(select(func.count()).select_from(FetchRunRecord))
            crawl_states = await session.scalar(select(func.count()).select_from(CrawlStateRecord))
        # end with
        await database.close()
        return int(credentials or 0), int(fetch_runs or 0), int(crawl_states or 0)
    # end def

    assert asyncio.run(local_state_counts()) == (0, 0, 0)

    purged = runner.invoke(
        main,
        ["provider", "del", "--account", account.id, "--delete-history", "--no-input"],
    )

    assert purged.exit_code == 0
    assert "permanently deleted its history" in purged.output
    assert not paths.history.joinpath("v1", account.service, account.id).exists()
    try:
        ConfigStore(paths).get_account(account.id)
    except KeyError:
        pass
    else:
        raise AssertionError("purged account configuration still exists")
    # end try
# end def


def test_rename_updates_only_the_display_name(tmp_path: Path, monkeypatch) -> None:
    paths = configured_paths(tmp_path, monkeypatch)
    paths.ensure()
    account = ConfigStore(paths).create_account("codex", "app-server", "Old name", None, {})

    result = CliRunner().invoke(
        main, ["provider", "rename", "--account", account.id, "--name", "New name", "--no-input"]
    )

    assert result.exit_code == 0
    assert "Renamed Old name to New name." in result.output
    renamed = ConfigStore(paths).get_account(account.id)
    assert renamed.name == "New name"
    assert renamed.id == account.id
# end def


def test_mv_is_an_alias_for_rename(tmp_path: Path, monkeypatch) -> None:
    paths = configured_paths(tmp_path, monkeypatch)
    paths.ensure()
    account = ConfigStore(paths).create_account("codex", "app-server", "Old name", None, {})

    result = CliRunner().invoke(
        main, ["provider", "mv", "--account", account.id, "--name", "New name", "--no-input"]
    )

    assert result.exit_code == 0
    assert ConfigStore(paths).get_account(account.id).name == "New name"
# end def


def test_merge_moves_history_and_deletes_source(tmp_path: Path, monkeypatch) -> None:
    paths = configured_paths(tmp_path, monkeypatch)

    async def prepare() -> tuple[AccountConfig, AccountConfig]:
        paths.ensure()
        database = Database(paths)
        await database.migrate()
        credential_id = await database.put_credential("codex", "Source", {"token": "secret"})
        config = ConfigStore(paths)
        source = config.create_account("codex", "app-server", "Source", credential_id, {})
        target = config.create_account("codex", "app-server", "Target", None, {})
        now = datetime.now(UTC)
        history = HistoryStore(paths, database)
        await history.append_result(
            ProviderFetchResult(
                service=source.service,
                provider=source.provider,
                account_id=source.id,
                fetched_at=now,
                metrics=[
                    Metric(key="five-hours", name="Five hours", usage=Usage(percentage=42), observed_at=now)
                ],
            )
        )
        async with database.sessions() as session:
            session.add(
                CrawlStateRecord(account_id=source.id, next_run_at=now + timedelta(minutes=10))
            )
            await session.commit()
        # end with
        await database.close()
        return source, target
    # end def

    source, target = asyncio.run(prepare())
    result = CliRunner().invoke(
        main,
        ["provider", "merge", "--source", source.id, "--target", target.id, "--no-input"],
    )

    assert result.exit_code == 0
    assert "Merged Source into Target and deleted Source." in result.output

    try:
        ConfigStore(paths).get_account(source.id)
    except KeyError:
        pass
    else:
        raise AssertionError("merged source account configuration still exists")
    # end try

    async def moved_sample_count() -> int:
        database = Database(paths)
        async with database.sessions() as session:
            from ai_usage.orm import MetricSampleRecord

            count = await session.scalar(
                select(func.count())
                .select_from(MetricSampleRecord)
                .where(MetricSampleRecord.account_id == target.id)
            )
        # end with
        await database.close()
        return int(count or 0)
    # end def

    assert asyncio.run(moved_sample_count()) == 1
    assert not paths.history.joinpath("v1", source.service, source.id).exists()

    async def source_state_counts() -> tuple[int, int]:
        database = Database(paths)
        async with database.sessions() as session:
            credentials = await session.scalar(select(func.count()).select_from(CredentialRecord))
            crawl_states = await session.scalar(
                select(func.count()).select_from(CrawlStateRecord).where(CrawlStateRecord.account_id == source.id)
            )
        # end with
        await database.close()
        return int(credentials or 0), int(crawl_states or 0)
    # end def

    assert asyncio.run(source_state_counts()) == (0, 0)
# end def


def test_hosts_add_and_remove_round_trip(tmp_path: Path, monkeypatch) -> None:
    paths = configured_paths(tmp_path, monkeypatch)
    paths.ensure()
    account = ConfigStore(paths).create_account("codex", "app-server", "Personal", None, {})

    added = CliRunner().invoke(
        main,
        [
            "provider", "hosts", "add",
            "--account", account.id,
            "--hostname", "laptop",
            "--host-id", "host-1",
            "--no-input",
        ],
    )
    assert added.exit_code == 0
    assert "Added host laptop (host-1)" in added.output
    with_host = ConfigStore(paths).get_account(account.id)
    assert with_host.hosts == [("laptop", "host-1")]

    removed = CliRunner().invoke(
        main,
        [
            "provider", "hosts", "rm",
            "--account", account.id,
            "--hostname", "laptop",
            "--host-id", "host-1",
            "--no-input",
        ],
    )
    assert removed.exit_code == 0
    assert ConfigStore(paths).get_account(account.id).hosts is None
# end def
