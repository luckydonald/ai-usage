import pytest

from ai_usage.config import ConfigStore
from ai_usage.host_identity import (
    HostIdentity,
    HostIdentityAmbiguous,
    account_allows_host,
    add_host_to_account,
    host_is_enabled_anywhere,
    load_local_host_identity,
    remove_host_from_account,
    resolve_host_identity,
)
from tests.test_storage import temporary_paths


def test_resolve_generates_a_new_identity_when_nothing_is_configured(tmp_path) -> None:
    paths = temporary_paths(tmp_path)
    paths.ensure()
    config = ConfigStore(paths)

    identity = _run(resolve_host_identity(paths, config))

    assert identity.host_id
    assert load_local_host_identity(paths) == identity
# end def


def test_resolve_reuses_the_saved_local_identity(tmp_path) -> None:
    paths = temporary_paths(tmp_path)
    paths.ensure()
    config = ConfigStore(paths)
    first = _run(resolve_host_identity(paths, config))
    second = _run(resolve_host_identity(paths, config))

    assert first == second
# end def


def test_resolve_restores_a_single_hostname_match(tmp_path, monkeypatch) -> None:
    paths = temporary_paths(tmp_path)
    paths.ensure()
    monkeypatch.setattr("socket.gethostname", lambda: "laptop")
    config = ConfigStore(paths)
    account = config.create_account("codex", "app-server", "Personal", None, {})
    config.save_account(account.model_copy(update={"hosts": [("laptop", "known-host-id")]}))

    async def confirm_restore(host_id: str) -> bool:
        assert host_id == "known-host-id"
        return True
    # end def

    identity = _run(resolve_host_identity(paths, config, confirm_restore=confirm_restore))

    assert identity.host_id == "known-host-id"
# end def


def test_resolve_raises_on_ambiguous_match_without_a_chooser(tmp_path, monkeypatch) -> None:
    paths = temporary_paths(tmp_path)
    paths.ensure()
    monkeypatch.setattr("socket.gethostname", lambda: "laptop")
    config = ConfigStore(paths)
    account_a = config.create_account("codex", "app-server", "A", None, {})
    account_b = config.create_account("codex", "app-server", "B", None, {})
    config.save_account(account_a.model_copy(update={"hosts": [("laptop", "host-1")]}))
    config.save_account(account_b.model_copy(update={"hosts": [("laptop", "host-2")]}))

    with pytest.raises(HostIdentityAmbiguous):
        _run(resolve_host_identity(paths, config))
    # end with
# end def


def test_add_and_remove_host_round_trip(tmp_path) -> None:
    paths = temporary_paths(tmp_path)
    paths.ensure()
    config = ConfigStore(paths)
    account = config.create_account("codex", "app-server", "Personal", None, {})
    identity = HostIdentity(hostname="laptop", host_id="host-1")

    added = add_host_to_account(config, account, identity)
    assert account_allows_host(added, "host-1") is True
    assert account_allows_host(added, "other-host") is False

    removed = remove_host_from_account(config, added, "host-1")
    assert removed.hosts is None
    assert account_allows_host(removed, "anything") is True
# end def


def test_host_is_enabled_anywhere(tmp_path) -> None:
    paths = temporary_paths(tmp_path)
    paths.ensure()
    config = ConfigStore(paths)
    account = config.create_account("codex", "app-server", "Personal", None, {})
    unrestricted = [account]
    assert host_is_enabled_anywhere(unrestricted, "host-1") is False

    restricted = add_host_to_account(config, account, HostIdentity("laptop", "host-1"))
    assert host_is_enabled_anywhere([restricted], "host-1") is True
    assert host_is_enabled_anywhere([restricted], "other-host") is False
# end def


def _run(coroutine):
    import asyncio

    return asyncio.run(coroutine)
# end def
