"""Command-line interface."""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import click

from ai_usage.collector import Collector
from ai_usage.config import ConfigStore
from ai_usage.crawler import Crawler
from ai_usage.database import Database
from ai_usage.history import HistoryStore
from ai_usage.models import AccountConfig
from ai_usage.providers import built_in_registry
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
    secret_json: str | None,
    no_input: bool,
    dynamic_options: dict[str, Any],
) -> AccountConfig:
    provider = runtime.providers.get(service, provider_key)
    options = dict(dynamic_options)
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
    credential_id = None
    if secret_json:
        credential = json.loads(secret_json)
        credential_id = await runtime.database.put_credential(provider_key, name or service, credential)
    # end if
    account = runtime.config.create_account(
        service,
        provider_key,
        name or f"{provider.display_name}",
        credential_id,
        options,
    )
    if account.service == "claude" and account.provider == "statusline":
        account.options.setdefault(
            "relay_file", str(runtime.paths.local / "relay" / f"{account.id}.json")
        )
        runtime.config.save_account(account)
        install_status_relay(account, runtime.paths.local)
    # end if
    return account
# end def


@click.group(invoke_without_command=True)
@click.pass_context
def main(context: click.Context) -> None:
    """Collect and visualize AI service usage."""
    if context.invoked_subcommand is None:
        context.invoke(run_all)
    # end if
# end def


@main.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.argument("service")
@click.argument("provider")
@click.option("--name")
@click.option("--secret-json", help="Credential JSON to encrypt in local SQLite.")
@click.option(
    "--secret-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Read credential JSON from a file instead of exposing it in shell history.",
)
@click.option("--no-input", is_flag=True)
@click.pass_context
def add(
    context: click.Context,
    service: str,
    provider: str,
    name: str | None,
    secret_json: str | None,
    secret_file: Path | None,
    no_input: bool,
) -> None:
    """Add a configured provider account."""
    async def execute() -> None:
        runtime = Runtime(default_paths())
        try:
            await runtime.initialize()
            account = await create_account(
                runtime,
                service,
                provider,
                name,
                credential_payload(secret_json, secret_file),
                no_input,
                parse_dynamic_options(tuple(context.args)),
            )
            click.echo(f"Added {account.name} ({account.id})")
        finally:
            await runtime.close()
        # end try
    # end def

    asyncio.run(execute())
# end def


@main.command("providers")
def list_providers() -> None:
    """List installed provider adapters."""
    registry = built_in_registry()
    for (service, key), provider in sorted(registry.providers.items()):
        marker = " [experimental]" if provider.experimental else ""
        click.echo(f"{service}/{key}: {provider.display_name}{marker}")
    # end for
# end def


@main.command()
@click.argument("service")
@click.argument("provider_key")
def discover(service: str, provider_key: str) -> None:
    """Show local accounts a provider can import."""
    async def execute() -> None:
        registry = built_in_registry()
        candidates = await registry.get(service, provider_key).discover()
        if not candidates:
            click.echo("No local accounts discovered")
        # end if
        for candidate in candidates:
            click.echo(json.dumps(candidate.model_dump(mode="json"), sort_keys=True))
        # end for
    # end def

    asyncio.run(execute())
# end def


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
                if result.error:
                    click.echo(f"ERROR {result.service}/{result.account_id}: {result.error}", err=True)
                else:
                    values = ", ".join(
                        f"{metric.name}={metric.usage.percentage:.1f}%" for metric in result.metrics
                    )
                    click.echo(f"{result.service}/{result.account_id}: {values}")
                # end if
            # end for
            if results and all(result.error for result in results):
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


@main.command("run-all")
@click.option("--host", default="localhost")
@click.option("--port", default=4458, type=int)
@click.option("--detach", "detach_mode", "-d", is_flag=True)
def run_all(host: str, port: int, detach_mode: bool) -> None:
    """Run crawling and the dashboard server together."""
    paths = default_paths()
    if detach_mode:
        click.echo(f"Detached as PID {detach(['run-all', '--host', host, '--port', str(port)], paths)}")
        return
    # end if
    try:
        from ai_usage.api import run_server_and_crawler
    except ImportError as exception:
        raise click.ClickException("the API server has not been installed") from exception
    # end try
    asyncio.run(run_server_and_crawler(paths, host, port, reporter=click.echo))
# end def


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
