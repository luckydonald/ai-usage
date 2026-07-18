"""Command-line interface."""

import asyncio
import json
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

import click
import typer

from ai_usage.collector import Collector
from ai_usage.config import ConfigStore
from ai_usage.crawler import Crawler
from ai_usage.database import Database
from ai_usage.history import HistoryStore
from ai_usage.host_identity import (
    HostIdentity,
    HostIdentityAmbiguous,
    add_host_to_account,
    any_account_restricts_hosts,
    generate_host_id,
    host_is_enabled_anywhere,
    load_local_host_identity,
    local_host_identity_path,
    remove_host_from_account,
    resolve_host_identity,
    save_local_host_identity,
)
from ai_usage.models import AccountConfig, FetchStatus
from ai_usage.provider_accounts import (
    AccountStatus,
    account_status,
    matching_accounts,
    merge_account_history,
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

app = typer.Typer(
    context_settings={"max_content_width": 120},
    rich_markup_mode=None,
    add_completion=False,
)
provider_app = typer.Typer(rich_markup_mode=None)
app.add_typer(provider_app, name="provider", help="Discover and manage configured provider accounts.")
hosts_app = typer.Typer(rich_markup_mode=None)
provider_app.add_typer(
    hosts_app, name="hosts", help="Manage which machines are allowed to crawl an account."
)
config_app = typer.Typer(rich_markup_mode=None)
app.add_typer(
    config_app, name="config", help="View and change shared settings stored in config.yml."
)
config_git_app = typer.Typer(rich_markup_mode=None)
config_app.add_typer(
    config_git_app, name="git", help="Enable/disable the debounced git commit/push of the data directory."
)


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


@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context) -> None:
    """Collect and visualize AI service usage."""
    if ctx.invoked_subcommand is None:
        click.echo(status_summary())
        click.echo()
        click.echo(ctx.get_help())
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


@provider_app.command(
    "add", context_settings={"ignore_unknown_options": True, "allow_extra_args": True}
)
def provider_add(
    ctx: typer.Context,
    service: Annotated[str | None, typer.Argument()] = None,
    provider_key: Annotated[str | None, typer.Argument()] = None,
    name: Annotated[str | None, typer.Option("--name")] = None,
    secret_json: Annotated[
        str | None, typer.Option("--secret-json", help="Credential JSON to encrypt in local SQLite.")
    ] = None,
    secret_file: Annotated[
        Path | None,
        typer.Option(
            "--secret-file",
            exists=True,
            dir_okay=False,
            help="Read credential JSON from a file instead of exposing it in shell history.",
        ),
    ] = None,
    no_input: Annotated[bool, typer.Option("--no-input")] = False,
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
            dynamic_options = parse_dynamic_options(tuple(ctx.args))
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


@provider_app.command("discover")
def provider_discover(
    service: Annotated[str | None, typer.Argument()] = None,
    provider_key: Annotated[str | None, typer.Argument()] = None,
) -> None:
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


async def ensure_host_identity(runtime: "Runtime", no_input: bool) -> HostIdentity:
    """Resolve (and persist) this machine's host identity, prompting when the choice is ambiguous."""
    interactive = interactive_terminal(no_input)

    async def confirm_restore(host_id: str) -> bool:
        if not interactive:
            return True
        # end if
        return click.confirm(f"Restore this machine's identity as host {host_id}?", default=True)
    # end def

    async def choose_among(candidates: list[str]) -> str | None:
        options = [SelectionChoice(f"host-{index}", host_id) for index, host_id in enumerate(candidates)]
        options.append(SelectionChoice("new", "None, generate new"))
        selected = await select_choice(
            "Multiple host ids are registered under this hostname — choose one", options
        )
        if selected is None or selected == "new":
            return None
        # end if
        return candidates[int(selected.removeprefix("host-"))]
    # end def

    try:
        return await resolve_host_identity(
            runtime.paths,
            runtime.config,
            confirm_restore=confirm_restore,
            choose_among=choose_among if interactive else None,
        )
    except HostIdentityAmbiguous as exception:
        raise click.ClickException(
            f"{exception} Run interactively to pick one, or edit "
            f"{local_host_identity_path(runtime.paths)} manually to "
            '{"hostname": "...", "host_id": "..."}.'
        ) from exception
    # end try
# end def


async def run_provider_add_wizard(runtime: "Runtime") -> None:
    selected, selected_target = await select_discovered_account(runtime, None, None)
    if selected:
        resolved_service, resolved_provider = selected.service, selected.provider
    elif selected_target:
        resolved_service, resolved_provider = selected_target
    else:
        return
    # end if
    credential = selected.account.credential if selected else None
    account, action = await create_account(
        runtime, resolved_service, resolved_provider, None, credential, True, {}, discovered=selected
    )
    verb = {"added": "Added", "existing": "Already configured", "restored": "Restored"}[action]
    click.echo(f"{verb} {account.name} ({account.id})")
# end def


async def run_first_crawl_wizard(runtime: "Runtime", identity: HostIdentity, resume_label: str) -> None:
    """Guide onboarding a brand-new machine that isn't enabled for any host-restricted account yet."""
    while True:
        configured = runtime.config.list_accounts(False)
        done_label = "Exit" if not configured else "Done: finish and resume " + resume_label
        done_subtext = "exit without creating/selecting any service" if not configured else ""
        options = [
            SelectionChoice("enable", "Enable existing service on this device"),
            SelectionChoice("create", "Create new"),
            SelectionChoice("done", done_label, done_subtext),
        ]
        selected = await select_choice("This machine isn't enabled for any account yet", options)
        if selected in (None, "done"):
            return
        # end if
        if selected == "enable":
            sub_options = [SelectionChoice("back", "« back")]
            sub_options += [
                SelectionChoice(f"account-{index}", f"{account.service}/{account.provider} — {account.name}")
                for index, account in enumerate(configured)
            ]
            picked = await select_choice("Enable which account on this device?", sub_options)
            if picked and picked != "back":
                account = configured[int(picked.removeprefix("account-"))]
                updated = add_host_to_account(runtime.config, account, identity)
                click.echo(f"Enabled {updated.name} on this device.")
            # end if
        elif selected == "create":
            await run_provider_add_wizard(runtime)
        # end if
    # end while
# end def


async def ensure_ready_to_crawl(runtime: "Runtime", no_input: bool, resume_label: str) -> HostIdentity:
    identity = await ensure_host_identity(runtime, no_input)
    accounts = runtime.config.list_accounts(False)
    if any_account_restricts_hosts(accounts) and not host_is_enabled_anywhere(accounts, identity.host_id):
        if not interactive_terminal(no_input):
            raise click.ClickException(
                "this machine is not enabled for any host-restricted account yet; "
                "run interactively to onboard it, or use `ai-usage provider hosts add`."
            )
        # end if
        await run_first_crawl_wizard(runtime, identity, resume_label)
    # end if
    return identity
# end def


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


@provider_app.command("list")
def provider_list(
    service: Annotated[str | None, typer.Argument()] = None,
    provider_key: Annotated[str | None, typer.Argument()] = None,
) -> None:
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


@provider_app.command("status")
def provider_status(
    service: Annotated[str | None, typer.Argument()] = None,
    provider_key: Annotated[str | None, typer.Argument()] = None,
    account: Annotated[str | None, typer.Argument()] = None,
    account_option: Annotated[str | None, typer.Option("--account")] = None,
    no_input: Annotated[bool, typer.Option("--no-input")] = False,
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
            account_config = await resolve_account(
                runtime,
                service,
                provider_key,
                target_id,
                no_input,
                "inspect",
            )
            if account_config is not None:
                print_account_status(await account_status(runtime.database, account_config))
            # end if
        finally:
            await runtime.close()
        # end try
    # end def

    asyncio.run(execute())
# end def


@provider_app.command("remove")
def provider_remove(
    service: Annotated[str | None, typer.Argument()] = None,
    provider_key: Annotated[str | None, typer.Argument()] = None,
    account: Annotated[str | None, typer.Argument()] = None,
    account_option: Annotated[str | None, typer.Option("--account")] = None,
    delete_history: Annotated[bool, typer.Option("--delete-history")] = False,
    no_input: Annotated[bool, typer.Option("--no-input")] = False,
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
            account_config = await resolve_account(
                runtime,
                service,
                provider_key,
                target_id,
                no_input,
                "remove",
            )
            if account_config is None:
                return
            # end if
            purge = delete_history
            if interactive_terminal(no_input) and not delete_history:
                purge = click.confirm(
                    f"Also permanently delete {account_config.name}'s historical usage?",
                    default=False,
                )
            # end if
            if account_config.service == "claude" and account_config.provider == "statusline":
                remove_status_relay(account_config, runtime.paths.local)
            # end if
            await remove_local_state(runtime.database, account_config)
            removed = account_config.model_copy(
                update={
                    "enabled": False,
                    "removed_at": account_config.removed_at or datetime.now(UTC),
                    "credential_id": None,
                }
            )
            runtime.config.save_account(removed)
            if purge:
                await purge_history(runtime.paths, runtime.database, removed)
                runtime.config.delete_account(removed)
                click.echo(f"Removed {account_config.name} and permanently deleted its history.")
            else:
                click.echo(f"Removed {account_config.name}; historical usage was preserved.")
            # end if
        finally:
            await runtime.close()
        # end try
    # end def

    asyncio.run(execute())
# end def


@provider_app.command("rename")
def provider_rename(
    service: Annotated[str | None, typer.Argument()] = None,
    provider_key: Annotated[str | None, typer.Argument()] = None,
    account: Annotated[str | None, typer.Argument()] = None,
    account_option: Annotated[str | None, typer.Option("--account")] = None,
    new_name: Annotated[str, typer.Option("--name")] = ...,
    no_input: Annotated[bool, typer.Option("--no-input")] = False,
) -> None:
    """Rename a configured account's display name."""
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
            account_config = await resolve_account(
                runtime, service, provider_key, target_id, no_input, "rename"
            )
            if account_config is None:
                return
            # end if
            old_name = account_config.name
            renamed = account_config.model_copy(update={"name": new_name})
            runtime.config.save_account(renamed)
            click.echo(f"Renamed {old_name} to {new_name}.")
        finally:
            await runtime.close()
        # end try
    # end def

    asyncio.run(execute())
# end def


@provider_app.command("merge")
def provider_merge(
    source: Annotated[str | None, typer.Argument()] = None,
    target: Annotated[str | None, typer.Argument()] = None,
    source_option: Annotated[str | None, typer.Option("--source")] = None,
    target_option: Annotated[str | None, typer.Option("--target")] = None,
    no_input: Annotated[bool, typer.Option("--no-input")] = False,
) -> None:
    """Merge one account's history into another, then delete the source account."""
    source_id = requested_account_id(source, source_option)
    target_id = requested_account_id(target, target_option)

    async def execute() -> None:
        runtime = Runtime(default_paths())
        try:
            await runtime.initialize()
            source_account = await resolve_account(runtime, None, None, source_id, no_input, "merge from")
            if source_account is None:
                return
            # end if
            target_account = await resolve_account(
                runtime, source_account.service, None, target_id, no_input, "merge into"
            )
            if target_account is None:
                return
            # end if
            if target_account.id == source_account.id:
                raise click.ClickException("source and target accounts must be different")
            # end if
            if interactive_terminal(no_input) and not click.confirm(
                f"Merge {source_account.name}'s history into {target_account.name} "
                f"and delete {source_account.name}?",
                default=False,
            ):
                return
            # end if
            await merge_account_history(runtime.paths, runtime.database, source_account, target_account)
            if source_account.service == "claude" and source_account.provider == "statusline":
                remove_status_relay(source_account, runtime.paths.local)
            # end if
            runtime.config.delete_account(source_account)
            click.echo(f"Merged {source_account.name} into {target_account.name} and deleted {source_account.name}.")
        finally:
            await runtime.close()
        # end try
    # end def

    asyncio.run(execute())
# end def


def _default_host_identity(paths: Paths, hostname: str | None, host_id: str | None) -> HostIdentity:
    if hostname and host_id:
        return HostIdentity(hostname=hostname, host_id=host_id)
    # end if
    if hostname or host_id:
        raise click.UsageError("--hostname and --host-id must be given together")
    # end if
    identity = load_local_host_identity(paths)
    if identity is None:
        identity = HostIdentity(hostname=socket.gethostname(), host_id=generate_host_id())
        save_local_host_identity(paths, identity)
    # end if
    return identity
# end def


@hosts_app.command("add")
def provider_hosts_add(
    service: Annotated[str | None, typer.Argument()] = None,
    provider_key: Annotated[str | None, typer.Argument()] = None,
    account: Annotated[str | None, typer.Argument()] = None,
    account_option: Annotated[str | None, typer.Option("--account")] = None,
    hostname: Annotated[
        str | None, typer.Option("--hostname", help="Defaults to this machine's hostname.")
    ] = None,
    host_id: Annotated[
        str | None,
        typer.Option("--host-id", help="Defaults to this machine's local host id (generated if missing)."),
    ] = None,
    no_input: Annotated[bool, typer.Option("--no-input")] = False,
) -> None:
    """Allow a machine to crawl this account (adds to its host allow-list)."""
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
            selected = await resolve_account(
                runtime, service, provider_key, target_id, no_input, "add a host to"
            )
            if selected is None:
                return
            # end if
            identity = _default_host_identity(runtime.paths, hostname, host_id)
            updated = add_host_to_account(runtime.config, selected, identity)
            click.echo(f"Added host {identity.hostname} ({identity.host_id}) to {updated.name}.")
        finally:
            await runtime.close()
        # end try
    # end def

    asyncio.run(execute())
# end def


@hosts_app.command("remove")
def provider_hosts_remove(
    service: Annotated[str | None, typer.Argument()] = None,
    provider_key: Annotated[str | None, typer.Argument()] = None,
    account: Annotated[str | None, typer.Argument()] = None,
    account_option: Annotated[str | None, typer.Option("--account")] = None,
    hostname: Annotated[
        str | None, typer.Option("--hostname", help="Defaults to this machine's hostname.")
    ] = None,
    host_id: Annotated[
        str | None, typer.Option("--host-id", help="Defaults to this machine's local host id.")
    ] = None,
    no_input: Annotated[bool, typer.Option("--no-input")] = False,
) -> None:
    """Disallow a machine from crawling this account (removes it from the host allow-list)."""
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
            selected = await resolve_account(
                runtime, service, provider_key, target_id, no_input, "remove a host from"
            )
            if selected is None:
                return
            # end if
            identity = _default_host_identity(runtime.paths, hostname, host_id)
            updated = remove_host_from_account(runtime.config, selected, identity.host_id)
            click.echo(f"Removed host {identity.hostname} ({identity.host_id}) from {updated.name}.")
        finally:
            await runtime.close()
        # end try
    # end def

    asyncio.run(execute())
# end def


@app.command()
def fetch(
    account_ids: Annotated[list[str], typer.Option("--account")] = [],  # noqa: B006
) -> None:
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


@app.command()
def crawl(
    detach_mode: Annotated[bool, typer.Option("--detach", "-d")] = False,
    no_input: Annotated[bool, typer.Option("--no-input")] = False,
) -> None:
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
            identity = await ensure_ready_to_crawl(runtime, no_input, "crawling")
            crawler = Crawler(
                runtime.collector,
                runtime.config,
                runtime.database,
                reporter=click.echo,
                host_id=identity.host_id,
            )
            await crawler.run()
        finally:
            await runtime.close()
        # end try
    # end def

    asyncio.run(execute())
# end def


@app.command("ingest-claude")
def ingest_claude(account_id: Annotated[str, typer.Argument()]) -> None:
    """Receive one Claude status-line JSON document on stdin."""
    paths = default_paths()
    payload = json.load(sys.stdin)
    target = paths.local / "relay" / f"{account_id}.json"
    write_relay_payload(target, payload)
# end def


@app.command("claude-relay-install")
def claude_relay_install(account_id: Annotated[str, typer.Argument()]) -> None:
    """Install or repair the composable Claude status-line relay."""
    runtime = Runtime(default_paths())
    account = runtime.config.get_account(account_id)
    target = install_status_relay(account, runtime.paths.local)
    click.echo(f"Installed relay in {target}")
# end def


@app.command("claude-relay-remove")
def claude_relay_remove(account_id: Annotated[str, typer.Argument()]) -> None:
    """Restore the status line that preceded the AI Usage relay."""
    runtime = Runtime(default_paths())
    account = runtime.config.get_account(account_id)
    remove_status_relay(account, runtime.paths.local)
    click.echo("Claude status-line relay removed")
# end def


@app.command()
def install(
    enable_server: Annotated[bool, typer.Option("--serve/--no-serve")] = True,
    host: Annotated[str, typer.Option("--host")] = "localhost",
    port: Annotated[int, typer.Option("--port")] = 4458,
) -> None:
    """Install a user-level startup service."""
    target = install_service(default_paths(), enable_server, host, port)
    click.echo(f"Installed {target}")
# end def


@app.command()
def completion(
    shell: Annotated[
        str | None,
        typer.Option(
            "--shell",
            click_type=click.Choice(["bash", "zsh", "fish"]),
            help="Shell to install completion for. Defaults to $SHELL.",
        ),
    ] = None,
) -> None:
    """Install shell tab-completion. Safe to re-run."""
    result = install_completion(default_paths(), main, shell)
    if result.rc_path is not None:
        click.echo(f"Wrote {result.script_path} and sourced it from {result.rc_path}")
        click.echo("Restart your shell (or `source` the rc file) to use it.")
    else:
        click.echo(f"Wrote {result.script_path}")
    # end if
# end def


@app.command("uninstall")
def uninstall() -> None:
    """Remove the user-level startup service without deleting data."""
    uninstall_service(default_paths())
    click.echo("Startup service removed")
# end def


@config_git_app.command("enable")
def config_git_enable() -> None:
    """Turn on the debounced git commit/push of the data directory."""
    paths = default_paths()
    paths.ensure()
    ConfigStore(paths).save_global_config({"git": {"enabled": True}})
    click.echo("Git backup enabled.")
# end def


@config_git_app.command("disable")
def config_git_disable() -> None:
    """Turn off the debounced git commit/push of the data directory."""
    paths = default_paths()
    paths.ensure()
    ConfigStore(paths).save_global_config({"git": {"enabled": False}})
    click.echo("Git backup disabled.")
# end def


@config_git_app.command("status")
def config_git_status() -> None:
    """Show whether git backup is currently enabled."""
    paths = default_paths()
    paths.ensure()
    state = "enabled" if ConfigStore(paths).structured_global_config().git.enabled else "disabled"
    click.echo(f"Git backup is {state}.")
# end def


@app.command("db-upgrade")
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


@app.command("history-cleanup")
def history_cleanup(
    older_than_days: Annotated[int, typer.Option("--older-than-days", show_default=True)] = 7,
) -> None:
    """Drop consecutive same-value history lines older than N days, keeping the first and last of each run."""
    async def execute() -> None:
        runtime = Runtime(default_paths())
        try:
            await runtime.initialize()
            summary = await runtime.history.dedup(older_than_days=older_than_days)
            click.echo(
                f"Removed {summary['removed_lines']} duplicate line(s) across {summary['touched_files']} file(s)."
            )
        finally:
            await runtime.close()
        # end try
    # end def

    asyncio.run(execute())
# end def


@app.command("up")
def run_all(
    host: Annotated[str, typer.Option("--host")] = "localhost",
    port: Annotated[int | None, typer.Option("--port")] = None,
    detach_mode: Annotated[bool, typer.Option("--detach", "-d")] = False,
    no_input: Annotated[bool, typer.Option("--no-input")] = False,
) -> None:
    """Run crawling and the dashboard server together."""
    from ai_usage.api import DEFAULT_PORT

    explicit_port = port is not None
    port = port if port is not None else DEFAULT_PORT
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

    async def execute() -> None:
        runtime = Runtime(paths)
        try:
            await runtime.initialize()
            identity = await ensure_ready_to_crawl(runtime, no_input, "up")
        finally:
            await runtime.close()
        # end try
        await run_server_and_crawler(
            paths,
            host,
            port,
            reporter=click.echo,
            explicit_port=explicit_port,
            host_id=identity.host_id,
        )
    # end def

    asyncio.run(execute())
# end def


@app.command()
def serve(
    host: Annotated[str, typer.Option("--host")] = "localhost",
    port: Annotated[int | None, typer.Option("--port")] = None,
) -> None:
    """Serve the usage API and dashboard without crawling."""
    import uvicorn

    from ai_usage.api import DEFAULT_PORT, create_app, exposed_host, resolve_port

    if exposed_host(host):
        click.echo(
            "WARNING: serving usage data on a non-loopback address without authentication",
            err=True,
        )
    # end if
    explicit_port = port is not None
    port = resolve_port(host, port if port is not None else DEFAULT_PORT, explicit_port)

    async def execute() -> None:
        server_app = create_app(default_paths())
        server = uvicorn.Server(uvicorn.Config(server_app, host=host, port=port))
        server_app.state.runtime.server = server
        await server.serve()
    # end def

    asyncio.run(execute())
# end def


main = typer.main.get_command(app)
main.add_command(main.commands["up"], "start")
main.add_command(main.commands["uninstall"], "deinstall")

_provider_click = main.commands["provider"]
_provider_click.add_command(_provider_click.commands["add"], "new")
_provider_click.add_command(_provider_click.commands["list"], "ls")
_provider_click.add_command(_provider_click.commands["status"], "info")
_provider_click.add_command(_provider_click.commands["remove"], "del")
_provider_click.add_command(_provider_click.commands["remove"], "rm")
_provider_click.add_command(_provider_click.commands["rename"], "name")
_provider_click.add_command(_provider_click.commands["rename"], "mv")

_hosts_click = _provider_click.commands["hosts"]
_hosts_click.add_command(_hosts_click.commands["remove"], "rm")


if __name__ == "__main__":
    main()
# end if
