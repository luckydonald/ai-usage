"""Command-line interface."""

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import click

from ai_usage.collector import Collector
from ai_usage.config import ConfigStore
from ai_usage.crawler import Crawler
from ai_usage.database import Database
from ai_usage.history import HistoryStore
from ai_usage.models import AccountConfig, FetchStatus
from ai_usage.provider_accounts import (
    AccountStatus,
    account_status,
    matching_accounts,
    purge_history,
    remove_local_state,
)
from ai_usage.provider_discovery import (
    DiscoveryChoice,
    DiscoveryFailure,
    discover_accounts,
    matching_providers,
)
from ai_usage.provider_tui import SelectionChoice, select_choice
from ai_usage.providers import Provider, ProviderRegistry, built_in_registry
from ai_usage.providers.claude import (
    install_status_relay,
    remove_status_relay,
    write_relay_payload,
)
from ai_usage.services import detach, install_service, uninstall_service
from ai_usage.settings import Paths, default_paths
from ai_usage.shell_completion import install_completion


class Runtime:
    def __init__(self, paths: Paths):
        paths.ensure()
        self.paths = paths
        self.database = Database(paths)
        self.config = ConfigStore(paths)
        self.history = HistoryStore(paths, self.database)
        self.providers = built_in_registry()
        self.collector = Collector(
            self.config,
            self.database,
            self.history,
            self.providers,
            reporter=click.echo,
        )
    # end def

    async def initialize(self) -> None:
        await self.database.migrate()
        await self.history.index_all()
    # end def

    async def close(self) -> None:
        await self.database.close()
    # end def
# end class


def parse_dynamic_options(arguments: tuple[str, ...]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if not argument.startswith("--"):
            raise click.UsageError(f"unexpected argument {argument!r}")
        # end if
        if "=" in argument:
            key, value = argument[2:].split("=", 1)
        else:
            key = argument[2:]
            index += 1
            if index >= len(arguments):
                raise click.UsageError(f"missing value for --{key}")
            # end if
            value = arguments[index]
        # end if
        parsed[key.replace("-", "_")] = value
        index += 1
    # end while
    return parsed
# end def


def credential_payload(secret_json: str | None, secret_file: Path | None) -> str | None:
    if secret_json and secret_file:
        raise click.UsageError("use either --secret-json or --secret-file, not both")
    # end if
    if secret_file:
        return secret_file.read_text(encoding="utf-8")
    # end if
    return secret_json
# end def


async def create_account(
    runtime: Runtime,
    service: str,
    provider_key: str,
    name: str | None,
    credential: dict[str, Any] | None,
    no_input: bool,
    dynamic_options: dict[str, Any],
    discovered: DiscoveryChoice | None = None,
) -> tuple[AccountConfig, Literal["added", "existing", "restored"]]:
    provider = runtime.providers.get(service, provider_key)
    options = dict(discovered.account.options) if discovered else {}
    options.update(dynamic_options)
    for field in provider.configuration_fields:
        if field.key not in options and field.default is not None:
            options[field.key] = field.default
        # end if
        if field.key not in options and field.required:
            if no_input:
                raise click.UsageError(f"missing required option --{field.key.replace('_', '-')}")
            # end if
            options[field.key] = click.prompt(field.label, hide_input=field.kind == "secret")
        # end if
        if field.kind == "integer" and field.key in options:
            options[field.key] = int(options[field.key])
        elif field.kind == "boolean" and field.key in options:
            options[field.key] = str(options[field.key]).casefold() in {"1", "true", "yes", "on"}
        # end if
    # end for
    fingerprint = discovered.fingerprint if discovered else None
    existing = (
        runtime.config.find_discovered_account(
            service,
            provider_key,
            fingerprint,
            discovered.account.options,
        )
        if fingerprint and discovered
        else None
    )
    if existing and existing.removed_at is None:
        if existing.discovery_fingerprint is None:
            existing = existing.model_copy(update={"discovery_fingerprint": fingerprint})
            runtime.config.save_account(existing)
        # end if
        return existing, "existing"
    # end if
    account_name = name or (discovered.account.name if discovered else provider.display_name)
    credential_id: str | None = None
    if credential:
        credential_id = await runtime.database.put_credential(provider_key, account_name, credential)
    # end if
    if existing:
        account = existing.model_copy(
            update={
                "name": account_name,
                "enabled": True,
                "removed_at": None,
                "credential_id": credential_id,
                "options": options,
                "discovery_fingerprint": fingerprint,
            }
        )
        runtime.config.save_account(account)
        action: Literal["added", "existing", "restored"] = "restored"
    else:
        account = runtime.config.create_account(
            service,
            provider_key,
            account_name,
            credential_id,
            options,
            discovery_fingerprint=fingerprint,
        )
        action = "added"
    # end if
    if account.service == "claude" and account.provider == "statusline":
        account.options.setdefault(
            "relay_file", str(runtime.paths.local / "relay" / f"{account.id}.json")
        )
        runtime.config.save_account(account)
        install_status_relay(account, runtime.paths.local)
    # end if
    return account, action
# end def


@click.group(invoke_without_command=True, context_settings={"max_content_width": 120})
@click.pass_context
def main(context: click.Context) -> None:
    """Collect and visualize AI service usage."""
    if context.invoked_subcommand is None:
        click.echo(status_summary())
        click.echo()
        click.echo(context.get_help())
    # end if
# end def


def status_summary() -> str:
    async def collect() -> str:
        paths = default_paths()
        paths.ensure()
        database = Database(paths)
        config = ConfigStore(paths)
        try:
            await database.migrate()
            accounts = config.list_accounts(enabled_only=True)
            from sqlalchemy import func, select

            from ai_usage.orm import FetchRunRecord

            async with database.sessions() as session:
                result = await session.execute(
                    select(func.max(FetchRunRecord.finished_at)).where(FetchRunRecord.success.is_(True))
                )
                last_crawl = result.scalar_one_or_none()
            # end async with
        finally:
            await database.close()
        # end try
        last_crawl_text = last_crawl.isoformat() if last_crawl else "never"
        return f"{len(accounts)} account(s) configured. Last successful crawl: {last_crawl_text}."
    # end def

    return asyncio.run(collect())
# end def


@main.group("provider")
def provider_group() -> None:
    """Discover and manage configured provider accounts."""
# end def


def interactive_terminal(no_input: bool) -> bool:
    return not no_input and sys.stdin.isatty() and sys.stdout.isatty()
# end def


def parsed_credential(secret_json: str | None, secret_file: Path | None) -> dict[str, Any] | None:
    payload = credential_payload(secret_json, secret_file)
    if payload is None:
        return None
    # end if
    parsed: dict[str, Any] = json.loads(payload)
    return parsed
# end def


def print_discovery_choices(
    choices: list[DiscoveryChoice],
    manual_providers: list[Provider] | None = None,
) -> None:
    if choices:
        click.echo("Discovered accounts:")
        for index, choice in enumerate(choices, start=1):
            click.echo(f"  {index}. {choice.label}")
        # end for
    else:
        click.echo("No local accounts discovered")
    # end if
    if manual_providers:
        click.echo("Manual provider adapters:")
        for provider in manual_providers:
            marker = " [experimental]" if provider.experimental else ""
            click.echo(
                f"  {provider.service}/{provider.key}: {provider.display_name}{marker}"
            )
        # end for
    # end if
# end def


async def discover_or_error(
    registry: ProviderRegistry,
    service: str | None,
    provider_key: str | None,
) -> tuple[list[DiscoveryChoice], list[DiscoveryFailure]]:
    try:
        return await discover_accounts(registry, service, provider_key)
    except KeyError as exception:
        raise click.ClickException(str(exception)) from exception
    # end try
# end def


async def select_discovered_account(
    runtime: Runtime,
    service: str | None,
    provider_key: str | None,
    discovered_choices: list[DiscoveryChoice] | None = None,
) -> tuple[DiscoveryChoice | None, tuple[str, str] | None]:
    choices = discovered_choices
    if choices is None:
        choices, failures = await discover_or_error(runtime.providers, service, provider_key)
        for failure in failures:
            click.echo(f"WARNING {failure.service}/{failure.provider}: {failure.error}", err=True)
        # end for
    # end if
    options = [
        SelectionChoice(f"discovered-{index}", choice.label, choice.provider_name)
        for index, choice in enumerate(choices)
    ]
    options.append(SelectionChoice("manual", "Manually configure other…"))
    selected = await select_choice("Choose an account to add", options)
    if selected is None:
        return None, None
    # end if
    if selected != "manual":
        return choices[int(selected.removeprefix("discovered-"))], None
    # end if
    providers = matching_providers(runtime.providers, service, provider_key)
    manual_options = [
        SelectionChoice(
            f"provider-{index}",
            f"{provider.service}/{provider.key}",
            provider.display_name + (" [experimental]" if provider.experimental else ""),
        )
        for index, provider in enumerate(providers)
    ]
    manual = await select_choice("Choose a provider adapter", manual_options)
    if manual is None:
        return None, None
    # end if
    selected_provider = providers[int(manual.removeprefix("provider-"))]
    return None, (selected_provider.service, selected_provider.key)
# end def


@provider_group.command("add", context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.argument("service", required=False)
@click.argument("provider_key", required=False)
@click.option("--name")
@click.option("--secret-json", help="Credential JSON to encrypt in local SQLite.")
@click.option(
    "--secret-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Read credential JSON from a file instead of exposing it in shell history.",
)
@click.option("--no-input", is_flag=True)
@click.pass_context
def provider_add(
    context: click.Context,
    service: str | None,
    provider_key: str | None,
    name: str | None,
    secret_json: str | None,
    secret_file: Path | None,
    no_input: bool,
) -> None:
    """Add a configured provider account."""
    async def execute() -> None:
        if (service is None or provider_key is None) and not interactive_terminal(no_input):
            registry = built_in_registry()
            choices, failures = await discover_or_error(registry, service, provider_key)
            print_discovery_choices(
                choices,
                manual_providers=matching_providers(registry, service, provider_key),
            )
            for failure in failures:
                click.echo(f"WARNING {failure.service}/{failure.provider}: {failure.error}", err=True)
            # end for
            return
        # end if
        resolved_service = service
        resolved_provider = provider_key
        runtime = Runtime(default_paths())
        try:
            await runtime.initialize()
            dynamic_options = parse_dynamic_options(tuple(context.args))
            selected: DiscoveryChoice | None = None
            selected_target: tuple[str, str] | None = None
            if resolved_service is None or resolved_provider is None:
                selected, selected_target = await select_discovered_account(
                    runtime, resolved_service, resolved_provider
                )
            elif not dynamic_options and not secret_json and not secret_file:
                choices, failures = await discover_or_error(
                    runtime.providers, resolved_service, resolved_provider
                )
                for failure in failures:
                    click.echo(
                        f"WARNING {failure.service}/{failure.provider}: {failure.error}", err=True
                    )
                # end for
                if len(choices) == 1:
                    selected = choices[0]
                elif len(choices) > 1:
                    if not interactive_terminal(no_input):
                        print_discovery_choices(
                            choices,
                            manual_providers=matching_providers(
                                runtime.providers, resolved_service, resolved_provider
                            ),
                        )
                        return
                    # end if
                    selected, selected_target = await select_discovered_account(
                        runtime, resolved_service, resolved_provider, choices
                    )
                # end if
            # end if
            if selected:
                resolved_service = selected.service
                resolved_provider = selected.provider
            elif selected_target:
                resolved_service, resolved_provider = selected_target
            # end if
            if resolved_service is None or resolved_provider is None:
                return
            # end if
            credential = parsed_credential(secret_json, secret_file)
            if credential is None and selected is not None:
                credential = selected.account.credential
            # end if
            account, action = await create_account(
                runtime,
                resolved_service,
                resolved_provider,
                name,
                credential,
                no_input or not interactive_terminal(no_input),
                dynamic_options,
                discovered=selected,
            )
            verb = {"added": "Added", "existing": "Already configured", "restored": "Restored"}[
                action
            ]
            click.echo(f"{verb} {account.name} ({account.id})")
        finally:
            await runtime.close()
        # end try
    # end def

    asyncio.run(execute())
# end def


@provider_group.command("discover")
@click.argument("service", required=False)
@click.argument("provider_key", required=False)
def provider_discover(service: str | None, provider_key: str | None) -> None:
    """Show local accounts a provider can import."""
    async def execute() -> None:
        choices, failures = await discover_or_error(built_in_registry(), service, provider_key)
        print_discovery_choices(choices)
        for failure in failures:
            click.echo(f"WARNING {failure.service}/{failure.provider}: {failure.error}", err=True)
        # end for
    # end def

    asyncio.run(execute())
# end def


provider_group.add_command(provider_add, "new")


def account_state(account: AccountConfig) -> str:
    if account.removed_at is not None:
        return "removed"
    # end if
    return "active" if account.enabled else "disabled"
# end def


def print_accounts(accounts: list[AccountConfig]) -> None:
    if not accounts:
        click.echo("No configured accounts")
        return
    # end if
    click.echo(f"{'STATE':<10} {'SERVICE/PROVIDER':<30} {'NAME':<24} ACCOUNT")
    for account in accounts:
        click.echo(
            f"{account_state(account):<10} "
            f"{account.service + '/' + account.provider:<30} "
            f"{account.name:<24} {account.id}"
        )
    # end for
# end def


def requested_account_id(account_argument: str | None, account_option: str | None) -> str | None:
    if account_argument and account_option and account_argument != account_option:
        raise click.UsageError("positional ACCOUNT and --account refer to different accounts")
    # end if
    return account_option or account_argument
# end def


async def resolve_account(
    runtime: Runtime,
    service: str | None,
    provider_key: str | None,
    account_id: str | None,
    no_input: bool,
    action: str,
) -> AccountConfig | None:
    if account_id:
        try:
            account = runtime.config.get_account(account_id)
        except KeyError as exception:
            raise click.ClickException(str(exception)) from exception
        # end try
        if service is not None and account.service != service:
            raise click.ClickException(f"account {account_id} is not registered for service {service}")
        # end if
        if provider_key is not None and account.provider != provider_key:
            raise click.ClickException(
                f"account {account_id} is not registered for provider {provider_key}"
            )
        # end if
        return account
    # end if
    accounts = matching_accounts(runtime.config, service, provider_key)
    if service is not None and provider_key is not None and len(accounts) == 1:
        return accounts[0]
    # end if
    if not interactive_terminal(no_input):
        print_accounts(accounts)
        return None
    # end if
    if not accounts:
        click.echo("No configured accounts")
        return None
    # end if
    selection_accounts = {
        f"account-{index}": account for index, account in enumerate(accounts)
    }
    selected = await select_choice(
        f"Choose an account to {action}",
        [
            SelectionChoice(
                key,
                account.name,
                f"{account.service}/{account.provider} — {account_state(account)}",
            )
            for key, account in selection_accounts.items()
        ],
    )
    if selected is None:
        return None
    # end if
    return selection_accounts[selected]
# end def


@provider_group.command("list")
@click.argument("service", required=False)
@click.argument("provider_key", required=False)
def provider_list(service: str | None, provider_key: str | None) -> None:
    """List configured provider accounts."""
    paths = default_paths()
    print_accounts(matching_accounts(ConfigStore(paths), service, provider_key))
# end def


def render_time(value: datetime | None) -> str:
    if value is None:
        return "never"
    # end if
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    # end if
    return value.astimezone().isoformat(timespec="seconds")
# end def


def print_account_status(status: AccountStatus) -> None:
    account = status.account
    click.echo(f"Account: {account.name} ({account.id})")
    click.echo(f"Provider: {account.service}/{account.provider}")
    click.echo(f"State: {account_state(account)}")
    if account.removed_at:
        click.echo(f"Removed: {render_time(account.removed_at)}")
    # end if
    click.echo(f"Credential: {'available' if status.credential_available else 'none'}")
    click.echo("Options: " + json.dumps(account.options, sort_keys=True))
    if status.latest_metrics:
        click.echo("Latest usage:")
        for metric in status.latest_metrics:
            reset = f", resets {render_time(metric.reset_at)}" if metric.reset_at else ""
            click.echo(
                f"  {metric.name}: {metric.percentage:.1f}% at "
                f"{render_time(metric.observed_at)}{reset}"
            )
        # end for
    else:
        click.echo("Latest usage: no samples")
    # end if
    if status.last_fetch:
        outcome = "succeeded" if status.last_fetch.success else f"failed: {status.last_fetch.error}"
        click.echo(f"Last fetch: {outcome} at {render_time(status.last_fetch.started_at)}")
    else:
        click.echo("Last fetch: never")
    # end if
    if status.crawl_state and account.removed_at is None:
        click.echo(f"Next crawl: {render_time(status.crawl_state.next_run_at)}")
        if status.crawl_state.last_error:
            click.echo(f"Crawl error: {status.crawl_state.last_error}")
        # end if
    else:
        click.echo("Next crawl: not scheduled")
    # end if
# end def


@provider_group.command("status")
@click.argument("service", required=False)
@click.argument("provider_key", required=False)
@click.argument("account", required=False)
@click.option("--account", "account_option")
@click.option("--no-input", is_flag=True)
def provider_status(
    service: str | None,
    provider_key: str | None,
    account: str | None,
    account_option: str | None,
    no_input: bool,
) -> None:
    """Show stored status for a configured account."""
    target_id = requested_account_id(account, account_option)
    candidates = matching_accounts(ConfigStore(default_paths()), service, provider_key)
    if (
        target_id is None
        and not interactive_terminal(no_input)
        and not (service is not None and provider_key is not None and len(candidates) == 1)
    ):
        print_accounts(candidates)
        return
    # end if

    async def execute() -> None:
        runtime = Runtime(default_paths())
        try:
            await runtime.initialize()
            account = await resolve_account(
                runtime,
                service,
                provider_key,
                target_id,
                no_input,
                "inspect",
            )
            if account is not None:
                print_account_status(await account_status(runtime.database, account))
            # end if
        finally:
            await runtime.close()
        # end try
    # end def

    asyncio.run(execute())
# end def


@provider_group.command("remove")
@click.argument("service", required=False)
@click.argument("provider_key", required=False)
@click.argument("account", required=False)
@click.option("--account", "account_option")
@click.option("--delete-history", is_flag=True)
@click.option("--no-input", is_flag=True)
def provider_remove(
    service: str | None,
    provider_key: str | None,
    account: str | None,
    account_option: str | None,
    delete_history: bool,
    no_input: bool,
) -> None:
    """Remove an account, preserving history unless requested otherwise."""
    target_id = requested_account_id(account, account_option)
    candidates = matching_accounts(ConfigStore(default_paths()), service, provider_key)
    if (
        target_id is None
        and not interactive_terminal(no_input)
        and not (service is not None and provider_key is not None and len(candidates) == 1)
    ):
        print_accounts(candidates)
        return
    # end if

    async def execute() -> None:
        runtime = Runtime(default_paths())
        try:
            await runtime.initialize()
            account = await resolve_account(
                runtime,
                service,
                provider_key,
                target_id,
                no_input,
                "remove",
            )
            if account is None:
                return
            # end if
            purge = delete_history
            if interactive_terminal(no_input) and not delete_history:
                purge = click.confirm(
                    f"Also permanently delete {account.name}'s historical usage?",
                    default=False,
                )
            # end if
            if account.service == "claude" and account.provider == "statusline":
                remove_status_relay(account, runtime.paths.local)
            # end if
            await remove_local_state(runtime.database, account)
            removed = account.model_copy(
                update={
                    "enabled": False,
                    "removed_at": account.removed_at or datetime.now(UTC),
                    "credential_id": None,
                }
            )
            runtime.config.save_account(removed)
            if purge:
                await purge_history(runtime.paths, runtime.database, removed)
                runtime.config.delete_account(removed)
                click.echo(f"Removed {account.name} and permanently deleted its history.")
            else:
                click.echo(f"Removed {account.name}; historical usage was preserved.")
            # end if
        finally:
            await runtime.close()
        # end try
    # end def

    asyncio.run(execute())
# end def


provider_group.add_command(provider_list, "ls")
provider_group.add_command(provider_status, "info")
provider_group.add_command(provider_remove, "del")
provider_group.add_command(provider_remove, "rm")


@main.command()
@click.option("--account", "account_ids", multiple=True)
def fetch(account_ids: tuple[str, ...]) -> None:
    """Fetch every configured provider once."""
    async def execute() -> None:
        runtime = Runtime(default_paths())
        try:
            await runtime.initialize()
            accounts = runtime.config.list_accounts()
            if account_ids:
                accounts = [account for account in accounts if account.id in account_ids]
            # end if
            results = await runtime.collector.fetch_all(accounts)
            for result in results:
                if result.status == FetchStatus.ERROR:
                    click.echo(f"ERROR {result.service}/{result.account_id}: {result.error}", err=True)
                else:
                    values = ", ".join(
                        f"{metric.name}={metric.usage.percentage:.1f}%" for metric in result.metrics
                    )
                    if result.status == FetchStatus.STALE:
                        click.echo(f"{result.service}/{result.account_id}: {values} ({result.error})")
                    else:
                        click.echo(f"{result.service}/{result.account_id}: {values}")
                    # end if
                # end if
            # end for
            if results and all(result.status == FetchStatus.ERROR for result in results):
                raise click.ClickException("every configured provider failed")
            # end if
        finally:
            await runtime.close()
        # end try
    # end def

    asyncio.run(execute())
# end def


@main.command()
@click.option("--detach", "detach_mode", "-d", is_flag=True)
def crawl(detach_mode: bool) -> None:
    """Continuously refresh configured providers."""
    paths = default_paths()
    if detach_mode:
        click.echo(f"Detached as PID {detach(['crawl'], paths)}")
        return
    # end if

    async def execute() -> None:
        runtime = Runtime(paths)
        try:
            await runtime.initialize()
            crawler = Crawler(
                runtime.collector,
                runtime.config,
                runtime.database,
                reporter=click.echo,
            )
            await crawler.run()
        finally:
            await runtime.close()
        # end try
    # end def

    asyncio.run(execute())
# end def


@main.command("ingest-claude")
@click.argument("account_id")
def ingest_claude(account_id: str) -> None:
    """Receive one Claude status-line JSON document on stdin."""
    paths = default_paths()
    payload = json.load(sys.stdin)
    target = paths.local / "relay" / f"{account_id}.json"
    write_relay_payload(target, payload)
# end def


@main.command("claude-relay-install")
@click.argument("account_id")
def claude_relay_install(account_id: str) -> None:
    """Install or repair the composable Claude status-line relay."""
    runtime = Runtime(default_paths())
    account = runtime.config.get_account(account_id)
    target = install_status_relay(account, runtime.paths.local)
    click.echo(f"Installed relay in {target}")
# end def


@main.command("claude-relay-remove")
@click.argument("account_id")
def claude_relay_remove(account_id: str) -> None:
    """Restore the status line that preceded the AI Usage relay."""
    runtime = Runtime(default_paths())
    account = runtime.config.get_account(account_id)
    remove_status_relay(account, runtime.paths.local)
    click.echo("Claude status-line relay removed")
# end def


@main.command()
@click.option("--serve/--no-serve", "enable_server", default=True)
@click.option("--host", default="localhost")
@click.option("--port", default=4458, type=int)
def install(enable_server: bool, host: str, port: int) -> None:
    """Install a user-level startup service."""
    target = install_service(default_paths(), enable_server, host, port)
    click.echo(f"Installed {target}")
# end def


@main.command()
@click.option(
    "--shell",
    type=click.Choice(["bash", "zsh", "fish"]),
    default=None,
    help="Shell to install completion for. Defaults to $SHELL.",
)
def completion(shell: str | None) -> None:
    """Install shell tab-completion. Safe to re-run."""
    result = install_completion(default_paths(), main, shell)
    if result.rc_path is not None:
        click.echo(f"Wrote {result.script_path} and sourced it from {result.rc_path}")
        click.echo("Restart your shell (or `source` the rc file) to use it.")
    else:
        click.echo(f"Wrote {result.script_path}")
    # end if
# end def


@main.command("uninstall")
def uninstall() -> None:
    """Remove the user-level startup service without deleting data."""
    uninstall_service(default_paths())
    click.echo("Startup service removed")
# end def


main.add_command(uninstall, "deinstall")


@main.command("db-upgrade")
def db_upgrade() -> None:
    """Upgrade the local database to the latest Alembic revision."""
    async def execute() -> None:
        runtime = Runtime(default_paths())
        try:
            await runtime.database.migrate()
        finally:
            await runtime.close()
        # end try
    # end def

    asyncio.run(execute())
# end def


@main.command("up")
@click.option("--host", default="localhost")
@click.option("--port", default=4458, type=int)
@click.option("--detach", "detach_mode", "-d", is_flag=True)
def run_all(host: str, port: int, detach_mode: bool) -> None:
    """Run crawling and the dashboard server together."""
    paths = default_paths()
    if detach_mode:
        click.echo(f"Detached as PID {detach(['up', '--host', host, '--port', str(port)], paths)}")
        return
    # end if
    try:
        from ai_usage.api import run_server_and_crawler
    except ImportError as exception:
        raise click.ClickException("the API server has not been installed") from exception
    # end try
    asyncio.run(run_server_and_crawler(paths, host, port, reporter=click.echo))
# end def


main.add_command(run_all, "start")


@main.command()
@click.option("--host", default="localhost")
@click.option("--port", default=4458, type=int)
def serve(host: str, port: int) -> None:
    """Serve the usage API and dashboard without crawling."""
    import uvicorn

    from ai_usage.api import create_app, exposed_host

    if exposed_host(host):
        click.echo(
            "WARNING: serving usage data on a non-loopback address without authentication",
            err=True,
        )
    # end if
    uvicorn.run(create_app(default_paths()), host=host, port=port)
# end def


if __name__ == "__main__":
    main()
# end if
