from datetime import UTC, datetime
from typing import Any

import pytest

from ai_usage.models import AccountConfig, ProviderFetchResult
from ai_usage.provider_discovery import (
    discover_accounts,
    discovery_fingerprint,
    exclude_discovered,
    matching_providers,
)
from ai_usage.providers import Provider, ProviderRegistry
from ai_usage.providers.base import DiscoveredAccount


class DiscoveringProvider(Provider):
    service = "example"
    key = "local"
    display_name = "Local example"

    async def discover(self) -> list[DiscoveredAccount]:
        return [DiscoveredAccount(name="Example", options={"profile_dir": "/example"})]
    # end def

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        del credential
        return ProviderFetchResult(
            service=self.service,
            provider=self.key,
            account_id=account.id,
            fetched_at=datetime.now(UTC),
        )
    # end def
# end class


class FailingDiscoveryProvider(DiscoveringProvider):
    key = "failing"
    display_name = "Failing example"

    async def discover(self) -> list[DiscoveredAccount]:
        raise RuntimeError("discovery unavailable")
    # end def
# end class


@pytest.mark.asyncio
async def test_discovery_isolates_provider_failures() -> None:
    registry = ProviderRegistry()
    registry.register(DiscoveringProvider())
    registry.register(FailingDiscoveryProvider())

    choices, failures = await discover_accounts(registry)

    assert [choice.label for choice in choices] == ["Example — example/local"]
    assert failures[0].provider == "failing"
    assert failures[0].error == "discovery unavailable"
    assert choices[0].fingerprint == discovery_fingerprint(
        "example", "local", {"profile_dir": "/example"}
    )
# end def


@pytest.mark.asyncio
async def test_exclude_discovered_drops_already_discovered_adapters() -> None:
    registry = ProviderRegistry()
    registry.register(DiscoveringProvider())
    registry.register(FailingDiscoveryProvider())

    choices, _failures = await discover_accounts(registry)
    remaining = exclude_discovered(matching_providers(registry), choices)

    assert [implementation.key for implementation in remaining] == ["failing"]
# end def
