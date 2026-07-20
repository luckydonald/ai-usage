"""Provider discovery, candidate identity, and adapter filtering."""

import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from ai_usage.providers import Provider, ProviderRegistry
from ai_usage.providers.base import DiscoveredAccount


@dataclass(frozen=True, slots=True)
class DiscoveryChoice:
    service: str
    provider: str
    provider_name: str
    account: DiscoveredAccount

    @property
    def fingerprint(self) -> str:
        return discovery_fingerprint(self.service, self.provider, self.account.options)
    # end def

    @property
    def label(self) -> str:
        return f"{self.account.name} — {self.service}/{self.provider}"
    # end def
# end class


@dataclass(frozen=True, slots=True)
class DiscoveryFailure:
    service: str
    provider: str
    error: str
# end class


def discovery_fingerprint(service: str, provider: str, options: dict[str, Any]) -> str:
    payload = json.dumps(
        {"service": service, "provider": provider, "options": options},
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()
# end def


def matching_providers(
    registry: ProviderRegistry,
    service: str | None = None,
    provider: str | None = None,
) -> list[Provider]:
    matches = [
        implementation
        for (registered_service, registered_provider), implementation in registry.providers.items()
        if (service is None or registered_service == service)
        and (provider is None or registered_provider == provider)
    ]
    return sorted(matches, key=lambda implementation: (implementation.service, implementation.key))
# end def


def exclude_discovered(
    implementations: list[Provider],
    choices: list[DiscoveryChoice],
) -> list[Provider]:
    discovered = {(choice.service, choice.provider) for choice in choices}
    return [
        implementation
        for implementation in implementations
        if (implementation.service, implementation.key) not in discovered
    ]
# end def


async def discover_accounts(
    registry: ProviderRegistry,
    service: str | None = None,
    provider: str | None = None,
) -> tuple[list[DiscoveryChoice], list[DiscoveryFailure]]:
    implementations = matching_providers(registry, service, provider)
    if not implementations:
        target = "/".join(part for part in (service, provider) if part)
        raise KeyError(f"no provider adapters match {target or 'the requested filters'}")
    # end if

    results = await asyncio.gather(
        *(implementation.discover() for implementation in implementations),
        return_exceptions=True,
    )
    choices: list[DiscoveryChoice] = []
    failures: list[DiscoveryFailure] = []
    for implementation, result in zip(implementations, results, strict=True):
        if isinstance(result, BaseException):
            failures.append(
                DiscoveryFailure(
                    service=implementation.service,
                    provider=implementation.key,
                    error=str(result),
                )
            )
            continue
        # end if
        for account in result:
            choices.append(
                DiscoveryChoice(
                    service=implementation.service,
                    provider=implementation.key,
                    provider_name=implementation.display_name,
                    account=account,
                )
            )
        # end for
    # end for
    return choices, failures
# end def
