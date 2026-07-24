"""Assembled Claude `Provider`s: private web API, statusline (+ CLI fallback), `/usage` CLI."""

from typing import Any

from ai_usage.icons import IconRef
from ai_usage.models import AccountConfig, ProviderFetchResult
from ai_usage.providers.base import (
    ConfigurationField,
    FallbackUsageMethod,
    Provider,
    ProviderLoginError,
    canonical_login,
)
from ai_usage.providers.claude.login.local.settings_file import SettingsFileLogin
from ai_usage.providers.claude.login.web.cookie_capture import CookieCaptureLogin
from ai_usage.providers.claude.usage.cli.direct import DirectCliUsage
from ai_usage.providers.claude.usage.cli.interactive import InteractiveCliUsage
from ai_usage.providers.claude.usage.local.relay_file import RelayFileUsage
from ai_usage.providers.claude.usage.web.private_api import PrivateApiUsage


class ClaudeWebUsageProvider(Provider):
    service = "claude"
    key = "web"
    display_name = "Claude private web API"
    icon = IconRef(set="solid", name="globe")
    configuration_fields = (
        ConfigurationField(
            key="org_id",
            label="Claude organization UUID",
            help="Auto-detected after login when the account belongs to a single organization.",
        ),
    )
    login_url = "https://claude.ai/login"

    usage_method = PrivateApiUsage()
    login_methods = (CookieCaptureLogin(),)

    def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
        email = canonical_login(
            result.identity.email if result.identity else None, self.display_name
        )
        organization = canonical_login(account.options.get("org_id"), self.display_name)
        return email if email == organization else f"{email}|{organization}"
    # end def
# end class


class ClaudeStatusProvider(Provider):
    service = "claude"
    key = "statusline"
    display_name = "Claude status line with /usage fallback"
    icon = IconRef(set="solid", name="gauge")
    configuration_fields = (
        ConfigurationField(key="command", label="Claude executable", default="claude"),
        ConfigurationField(key="profile_dir", label="Claude profile", kind="path"),
        ConfigurationField(key="relay_file", label="Status relay file", kind="path"),
        ConfigurationField(key="stale_seconds", label="Relay staleness", kind="integer", default=120),
    )

    usage_method = FallbackUsageMethod((RelayFileUsage(), DirectCliUsage(), InteractiveCliUsage()))
    login_methods = (SettingsFileLogin(),)

    def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
        del account
        if result.identity is None:
            raise ProviderLoginError(f"{self.display_name} cannot determine the account login")
        # end if
        return canonical_login(result.identity.email, self.display_name)
    # end def
# end class


class ClaudeUsageProvider(ClaudeStatusProvider):
    key = "cli-usage"
    display_name = "Claude /usage"
    icon = IconRef(set="solid", name="terminal")

    usage_method = FallbackUsageMethod((DirectCliUsage(), InteractiveCliUsage()))

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        options = dict(account.options)
        options.pop("relay_file", None)
        direct = account.model_copy(update={"options": options})
        return await super().fetch(direct, credential)
    # end def
# end class
