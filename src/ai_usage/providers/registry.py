"""Provider registry with entry-point extensibility."""

from importlib.metadata import entry_points

from ai_usage.providers.base import Provider
from ai_usage.providers.claude import ClaudeStatusProvider, ClaudeUsageProvider
from ai_usage.providers.codex import CodexAppServerProvider, CodexStatusProvider
from ai_usage.providers.copilot import CopilotBillingProvider
from ai_usage.providers.web import ClaudeWebProvider, CodexWebProvider, CopilotEntitlementsProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self.providers: dict[tuple[str, str], Provider] = {}
    # end def

    def register(self, provider: Provider) -> None:
        identity = (provider.service, provider.key)
        if identity in self.providers:
            raise ValueError(f"provider {provider.service}/{provider.key} is already registered")
        # end if
        self.providers[identity] = provider
    # end def

    def get(self, service: str, provider: str) -> Provider:
        try:
            return self.providers[(service, provider)]
        except KeyError as exception:
            raise KeyError(f"unknown provider {service}/{provider}") from exception
        # end try
    # end def

    def load_entry_points(self) -> None:
        for entry_point in entry_points(group="ai_usage.providers"):
            loaded = entry_point.load()
            provider = loaded() if isinstance(loaded, type) else loaded
            self.register(provider)
        # end for
    # end def
# end class


def built_in_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    for provider in (
        CodexAppServerProvider(),
        CodexStatusProvider(),
        ClaudeStatusProvider(),
        ClaudeUsageProvider(),
        CopilotBillingProvider(),
        CodexWebProvider(),
        ClaudeWebProvider(),
        CopilotEntitlementsProvider(),
    ):
        registry.register(provider)
    # end for
    registry.load_entry_points()
    return registry
# end def
