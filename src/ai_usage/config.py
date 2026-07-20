"""YAML-backed account and interval configuration."""

import logging
import uuid
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from ai_usage.models import AccountConfig, GlobalConfig
from ai_usage.settings import Paths

LOGGER = logging.getLogger(__name__)

DEFAULT_INTERVALS = {
    "normal_seconds": 600,
    "active_seconds": 60,
    "active_for_seconds": 900,
    "maximum_backoff_seconds": 3600,
}


class ConfigStore:
    def __init__(self, paths: Paths):
        self.paths = paths
    # end def

    def global_config(self) -> dict[str, Any]:
        path = self.paths.root / "config.yml"
        if not path.exists():
            return {}
        # end if
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"{path} must contain a YAML object")
        # end if
        return loaded
    # end def

    def structured_global_config(self) -> GlobalConfig:
        """Validated view of `global_config()`; falls back to defaults on schema drift."""
        raw = self.global_config()
        try:
            return GlobalConfig.model_validate(raw)
        except ValidationError as exception:
            LOGGER.warning(
                "config.yml did not match the expected schema, falling back to defaults: %s",
                exception,
            )
            return GlobalConfig()
        # end try
    # end def

    def save_global_config(self, updates: dict[str, Any]) -> Path:
        """Merge `updates` into the existing `config.yml`, one top-level key at a time."""
        path = self.paths.root / "config.yml"
        merged = self.global_config()
        merged.update(updates)
        temporary = path.with_suffix(".yml.tmp")
        temporary.write_text(yaml.safe_dump(merged, sort_keys=False), encoding="utf-8")
        temporary.replace(path)
        return path
    # end def

    def list_accounts(self, enabled_only: bool = True) -> list[AccountConfig]:
        accounts: list[AccountConfig] = []
        if not self.paths.services.exists():
            return accounts
        # end if
        for path in sorted(self.paths.services.glob("*/*.yml")):
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
            account = AccountConfig.model_validate(loaded)
            if not enabled_only or account.enabled:
                accounts.append(account)
            # end if
        # end for
        return accounts
    # end def

    def get_account(self, account_id: str) -> AccountConfig:
        matches = [account for account in self.list_accounts(False) if account.id == account_id]
        if len(matches) != 1:
            raise KeyError(f"account {account_id} was not found")
        # end if
        return matches[0]
    # end def

    def save_account(self, account: AccountConfig) -> Path:
        directory = self.paths.services / account.service
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = directory / f"{account.id}.yml"
        temporary = path.with_suffix(".yml.tmp")
        temporary.write_text(
            yaml.safe_dump(account.model_dump(mode="json"), sort_keys=False),
            encoding="utf-8",
        )
        temporary.replace(path)
        return path
    # end def

    def delete_account(self, account: AccountConfig) -> None:
        path = self.paths.services / account.service / f"{account.id}.yml"
        if path.exists():
            path.unlink()
        # end if
    # end def

    def create_account(
        self,
        service: str,
        provider: str,
        name: str,
        credential_id: str | None,
        options: dict[str, Any],
        discovery_fingerprint: str | None = None,
    ) -> AccountConfig:
        account = AccountConfig(
            id=str(uuid.uuid7()),
            service=service,
            provider=provider,
            name=name,
            credential_id=credential_id,
            options=options,
            discovery_fingerprint=discovery_fingerprint,
        )
        self.save_account(account)
        return account
    # end def

    def find_discovered_account(
        self,
        service: str,
        provider: str,
        fingerprint: str,
        discovered_options: dict[str, Any],
    ) -> AccountConfig | None:
        accounts = self.list_accounts(False)
        matches = [
            account
            for account in accounts
            if account.discovery_fingerprint == fingerprint
        ]
        if not matches:
            matches = [
                account
                for account in accounts
                if account.discovery_fingerprint is None
                and account.service == service
                and account.provider == provider
                and all(account.options.get(key) == value for key, value in discovered_options.items())
            ]
        # end if
        if len(matches) > 1:
            raise ValueError(f"multiple accounts match discovered provider {service}/{provider}")
        # end if
        return matches[0] if matches else None
    # end def

    def group_accounts(self, account_ids: list[str]) -> str:
        """Link the given accounts as aliases of the same real-world account, sharing a `group_id`.

        Reuses an existing `group_id` if any of the accounts already has one, so grouping an
        already-grouped account with a new one extends the group instead of splitting it.
        """
        if len(account_ids) < 2:
            raise ValueError("grouping requires at least two accounts")
        # end if
        accounts = [self.get_account(account_id) for account_id in account_ids]
        existing_group_ids = {account.group_id for account in accounts if account.group_id}
        if len(existing_group_ids) > 1:
            raise ValueError("accounts already belong to different groups; ungroup them first")
        # end if
        group_id = next(iter(existing_group_ids), None) or str(uuid.uuid7())
        for account in accounts:
            if account.group_id != group_id:
                self.save_account(account.model_copy(update={"group_id": group_id}))
            # end if
        # end for
        return group_id
    # end def

    def ungroup_account(self, account_id: str) -> AccountConfig:
        account = self.get_account(account_id)
        updated = account.model_copy(update={"group_id": None})
        self.save_account(updated)
        return updated
    # end def

    def intervals_for(self, account: AccountConfig) -> dict[str, int]:
        global_config = self.global_config()
        merged = dict(DEFAULT_INTERVALS)
        layers = (
            global_config.get("intervals", {}),
            global_config.get("services", {}).get(account.service, {}).get("intervals", {}),
            global_config.get("providers", {}).get(account.provider, {}).get("intervals", {}),
            account.intervals,
        )
        for layer in layers:
            merged.update({key: int(value) for key, value in layer.items()})
        # end for
        return merged
    # end def
# end class
