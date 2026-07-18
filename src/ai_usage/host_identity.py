"""Per-machine identity used to scope which accounts crawl on which computer."""

import json
import socket
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from ai_usage.config import ConfigStore
from ai_usage.models import AccountConfig
from ai_usage.settings import Paths


@dataclass(frozen=True, slots=True)
class HostIdentity:
    hostname: str
    host_id: str
# end class


def local_host_identity_path(paths: Paths) -> Path:
    return paths.local / "host_id.json"
# end def


def load_local_host_identity(paths: Paths) -> HostIdentity | None:
    path = local_host_identity_path(paths)
    if not path.exists():
        return None
    # end if
    payload = json.loads(path.read_text(encoding="utf-8"))
    return HostIdentity(hostname=payload["hostname"], host_id=payload["host_id"])
# end def


def save_local_host_identity(paths: Paths, identity: HostIdentity) -> None:
    path = local_host_identity_path(paths)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"hostname": identity.hostname, "host_id": identity.host_id}),
        encoding="utf-8",
    )
# end def


def hostname_matches(accounts: list[AccountConfig], hostname: str) -> list[str]:
    """Distinct host_ids already registered under `hostname` across every account's `hosts` list."""
    seen: dict[str, None] = {}
    for account in accounts:
        for candidate_hostname, host_id in account.hosts or []:
            if candidate_hostname == hostname:
                seen.setdefault(host_id, None)
            # end if
        # end for
    # end for
    return list(seen)
# end def


def account_allows_host(account: AccountConfig, host_id: str) -> bool:
    if not account.hosts:
        return True
    # end if
    return any(candidate_host_id == host_id for _hostname, candidate_host_id in account.hosts)
# end def


def any_account_restricts_hosts(accounts: list[AccountConfig]) -> bool:
    return any(account.hosts for account in accounts)
# end def


def host_is_enabled_anywhere(accounts: list[AccountConfig], host_id: str) -> bool:
    return any(account_allows_host(account, host_id) and account.hosts for account in accounts)
# end def


def add_host_to_account(config: ConfigStore, account: AccountConfig, identity: HostIdentity) -> AccountConfig:
    hosts = list(account.hosts or [])
    if not any(host_id == identity.host_id for _hostname, host_id in hosts):
        hosts.append((identity.hostname, identity.host_id))
    # end if
    updated = account.model_copy(update={"hosts": hosts})
    config.save_account(updated)
    return updated
# end def


def remove_host_from_account(config: ConfigStore, account: AccountConfig, host_id: str) -> AccountConfig:
    hosts = [pair for pair in (account.hosts or []) if pair[1] != host_id]
    updated = account.model_copy(update={"hosts": hosts or None})
    config.save_account(updated)
    return updated
# end def


class HostIdentityAmbiguous(Exception):
    def __init__(self, hostname: str, candidates: list[str]):
        super().__init__(
            f"hostname {hostname!r} is registered under {len(candidates)} different host ids; "
            f"run interactively or configure {{local/host_id.json}} manually"
        )
        self.hostname = hostname
        self.candidates = candidates
    # end def
# end class


def generate_host_id() -> str:
    return str(uuid.uuid7())
# end def


async def resolve_host_identity(
    paths: Paths,
    config: ConfigStore,
    confirm_restore: Callable[[str], Awaitable[bool]] | None = None,
    choose_among: Callable[[list[str]], Awaitable[str | None]] | None = None,
) -> HostIdentity:
    """Resolve (and persist) this machine's host identity.

    `confirm_restore`/`choose_among` are injected so callers can drive an interactive
    prompt (TUI/click.confirm) without this module depending on click/textual directly.
    """
    existing = load_local_host_identity(paths)
    if existing is not None:
        return existing
    # end if

    hostname = socket.gethostname()
    accounts = config.list_accounts(False)
    candidates = hostname_matches(accounts, hostname)

    if len(candidates) == 1:
        host_id = candidates[0]
        restore = True
        if confirm_restore is not None:
            restore = await confirm_restore(host_id)
        # end if
        identity = HostIdentity(hostname=hostname, host_id=host_id if restore else generate_host_id())
        save_local_host_identity(paths, identity)
        return identity
    # end if

    if len(candidates) > 1:
        if choose_among is None:
            raise HostIdentityAmbiguous(hostname, candidates)
        # end if
        chosen = await choose_among(candidates)
        host_id = chosen if chosen is not None else generate_host_id()
        identity = HostIdentity(hostname=hostname, host_id=host_id)
        save_local_host_identity(paths, identity)
        return identity
    # end if

    identity = HostIdentity(hostname=hostname, host_id=generate_host_id())
    save_local_host_identity(paths, identity)
    return identity
# end def
