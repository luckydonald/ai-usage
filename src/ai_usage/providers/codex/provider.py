"""Assembled Codex `Provider`s wiring login methods to usage methods."""

from ai_usage.icons import IconRef
from ai_usage.models import AccountConfig, ProviderFetchResult
from ai_usage.providers.base import ConfigurationField, Provider, ProviderLoginError, canonical_login
from ai_usage.providers.codex.login.local.auth_json import AuthJsonLogin
from ai_usage.providers.codex.login.web.cookie_capture import CookieCaptureLogin
from ai_usage.providers.codex.usage.cli.app_server import AppServerUsage
from ai_usage.providers.codex.usage.cli.status_ptv import StatusPtyUsage
from ai_usage.providers.codex.usage.web.private_api import PrivateApiUsage


class CodexWebUsageProvider(Provider):
    service = "codex"
    key = "web"
    display_name = "Codex private web API"
    icon = IconRef(set="solid", name="globe")
    login_url = "https://chatgpt.com/"
    login_hint = "Click \"Log in\" once the page loads."

    usage_method = PrivateApiUsage()
    login_methods = (CookieCaptureLogin(),)

    def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
        del account
        return canonical_login(
            result.identity.email if result.identity else None, self.display_name
        )
    # end def
# end class


class CodexAppServerProvider(Provider):
    service = "codex"
    key = "app-server"
    display_name = "Codex app-server"
    icon = IconRef(set="solid", name="server")
    configuration_fields = (
        ConfigurationField(key="command", label="Codex executable", default="codex"),
        ConfigurationField(key="profile_dir", label="Codex profile", kind="path"),
    )

    usage_method = AppServerUsage()
    login_methods = (AuthJsonLogin(),)

    def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
        del account
        return canonical_login(
            result.identity.email if result.identity else None, self.display_name
        )
    # end def
# end class


class CodexStatusProvider(Provider):
    service = "codex"
    key = "cli-status"
    display_name = "Codex /status"
    icon = IconRef(set="solid", name="terminal")
    configuration_fields = (
        ConfigurationField(key="command", label="Codex executable", default="codex"),
    )

    usage_method = StatusPtyUsage()
    login_methods = ()

    def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
        del account, result
        raise ProviderLoginError(f"{self.display_name} cannot determine the account login")
    # end def
# end class
