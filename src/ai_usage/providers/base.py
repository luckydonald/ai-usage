"""Provider interface and discovery contracts."""

from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel

from ai_usage.icons import IconRef
from ai_usage.models import AccountConfig, ProviderFetchResult


class ProviderError(RuntimeError):
    pass
# end class


class ProviderLoginError(ProviderError):
    pass
# end class


def canonical_login(value: object, provider_name: str) -> str:
    if not isinstance(value, str) or not (login := value.strip()):
        raise ProviderLoginError(f"{provider_name} could not determine the account login")
    # end if
    return login.casefold()
# end def


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


CredentialKind = Literal["none", "bearer_token", "cookie_jar", "app_token"]


class LoginMethod(ABC):
    """One way to obtain or discover a credential usable by a `UsageMethod`."""

    key: str
    display_name: str
    credential_kind: CredentialKind = "none"

    async def discover(self) -> list[DiscoveredAccount]:
        return []
    # end def

    async def authenticate(self, options: dict[str, Any]) -> dict[str, Any] | None:
        del options
        raise ProviderLoginError(f"{self.display_name} does not support interactive login")
    # end def

    async def discover_options(self, credential: dict[str, Any] | None) -> dict[str, Any]:
        """Best-effort auto-fill for `configuration_fields` using an already-obtained credential."""
        del credential
        return {}
    # end def
# end class


class UsageMethod(ABC):
    """One way to fetch usage data given a resolved credential."""

    required_credential_kind: CredentialKind = "none"

    @abstractmethod
    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        raise NotImplementedError
    # end def
# end class


class FallbackUsageMethod(UsageMethod):
    """Tries each `UsageMethod` in order, returning the first successful result."""

    def __init__(self, methods: tuple[UsageMethod, ...]):
        if not methods:
            raise ValueError("FallbackUsageMethod requires at least one method")
        # end if
        self.methods = methods
        self.required_credential_kind = methods[0].required_credential_kind
    # end def

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        last_error: Exception | None = None
        for method in self.methods:
            try:
                return await method.fetch(account, credential)
            except ProviderError as e:
                last_error = e
                continue
            # end try
        # end for
        assert last_error is not None
        raise last_error
    # end def
# end class


class Provider(ABC):
    """Composition root: pairs a `UsageMethod` (the registry identity) with the
    `LoginMethod`s that can supply it a credential."""

    service: str
    key: str
    display_name: str
    experimental: bool = False
    configuration_fields: tuple[ConfigurationField, ...] = ()
    login_url: str | None = None
    login_hint: str | None = None
    icon: IconRef | None = None

    usage_method: UsageMethod
    login_methods: tuple[LoginMethod, ...] = ()

    @property
    def required_credential_kind(self) -> CredentialKind:
        return self.usage_method.required_credential_kind
    # end def

    def matching_login_methods(self) -> tuple[LoginMethod, ...]:
        return tuple(
            method for method in self.login_methods
            if method.credential_kind == self.required_credential_kind
        )
    # end def

    async def discover(self) -> list[DiscoveredAccount]:
        accounts: list[DiscoveredAccount] = []
        for method in self.matching_login_methods():
            accounts.extend(await method.discover())
        # end for
        return accounts
    # end def

    async def authenticate(self, options: dict[str, Any]) -> dict[str, Any] | None:
        methods = self.matching_login_methods()
        if not methods:
            return None
        # end if
        return await methods[0].authenticate(options)
    # end def

    async def discover_options(self, credential: dict[str, Any] | None) -> dict[str, Any]:
        """Best-effort auto-fill for `configuration_fields` using an already-obtained credential."""
        methods = self.matching_login_methods()
        if not methods:
            return {}
        # end if
        return await methods[0].discover_options(credential)
    # end def

    def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
        """Return the canonical login that identifies this provider configuration's real account."""
        del account, result
        raise NotImplementedError
    # end def

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        return await self.usage_method.fetch(account, credential)
    # end def
# end class
