"""Provider interface and discovery contracts."""

from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel

from ai_usage.models import AccountConfig, ProviderFetchResult


class ProviderError(RuntimeError):
    pass
# end class


class ConfigurationField(BaseModel):
    key: str
    label: str
    kind: Literal["string", "integer", "boolean", "secret", "path"] = "string"
    required: bool = False
    default: Any = None
    help: str = ""
# end class


class DiscoveredAccount(BaseModel):
    name: str
    options: dict[str, Any]
    credential: dict[str, Any] | None = None
# end class


class Provider(ABC):
    service: str
    key: str
    display_name: str
    experimental: bool = False
    configuration_fields: tuple[ConfigurationField, ...] = ()
    login_url: str | None = None

    async def discover(self) -> list[DiscoveredAccount]:
        return []
    # end def

    async def authenticate(self, options: dict[str, Any]) -> dict[str, Any] | None:
        del options
        return None
    # end def

    async def discover_options(self, credential: dict[str, Any] | None) -> dict[str, Any]:
        """Best-effort auto-fill for `configuration_fields` using an already-obtained credential."""
        del credential
        return {}
    # end def

    @abstractmethod
    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        raise NotImplementedError
    # end def
# end class

