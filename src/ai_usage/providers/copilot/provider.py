"""GitHub Copilot providers: assembled from login/usage methods."""

from ai_usage.icons import IconRef
from ai_usage.models import AccountConfig, ProviderFetchResult
from ai_usage.providers.base import ConfigurationField, Provider, ProviderLoginError, canonical_login
from ai_usage.providers.copilot.login.cli.token_reuse import TokenReuseLogin
from ai_usage.providers.copilot.usage.web.billing_api import BillingApiUsage
from ai_usage.providers.copilot.usage.web.entitlements import GenericPrivateWebUsage
from ai_usage.providers.copilot.usage.web.quota_api import QuotaApiUsage


class CopilotBillingProvider(Provider):
    service = "copilot"
    key = "github-api"
    display_name = "GitHub AI-credit billing API"
    icon = IconRef(set="brands", name="github")
    configuration_fields = (
        ConfigurationField(key="username", label="GitHub username", required=True),
        ConfigurationField(key="allowance", label="Monthly AI credits", kind="integer", required=True),
        ConfigurationField(key="billing_day", label="Billing cycle day", kind="integer", default=1),
        ConfigurationField(key="api_url", label="GitHub API URL", default="https://api.github.com"),
    )
    # No login methods: credential is supplied externally (CLI flag/manual entry),
    # matching the original `CopilotBillingProvider`, which had no `authenticate`/`discover`.
    usage_method = BillingApiUsage()
    login_methods = ()

    def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
        del result
        return canonical_login(account.options.get("username"), self.display_name)
    # end def
# end class


class CopilotStatusProvider(Provider):
    service = "copilot"
    key = "statusline"
    display_name = "Copilot CLI quota (local session)"
    icon = IconRef(set="brands", name="github")
    configuration_fields = (
        ConfigurationField(key="config_dir", label="Copilot CLI config directory", kind="path"),
        ConfigurationField(key="billing_day", label="Billing cycle day", kind="integer", default=1),
        ConfigurationField(key="api_url", label="GitHub API URL", default="https://api.github.com"),
    )
    usage_method = QuotaApiUsage()
    login_methods = (TokenReuseLogin(),)

    def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
        del account
        return canonical_login(
            result.identity.name if result.identity else None, self.display_name
        )
    # end def
# end class


class CopilotEntitlementsProvider(Provider):
    service = "copilot"
    key = "entitlements"
    display_name = "Copilot private entitlement API"
    icon = IconRef(set="solid", name="key")
    experimental = True
    configuration_fields = (
        ConfigurationField(key="endpoint", label="Private usage endpoint", required=True),
        ConfigurationField(key="percentage_field", label="Percentage JSON field", required=True),
        ConfigurationField(key="metric_key", label="Metric key", default="usage"),
        ConfigurationField(key="metric_name", label="Metric name", default="Usage"),
    )
    usage_method = GenericPrivateWebUsage(service=service, key=key)
    login_methods = ()

    def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
        del account, result
        raise ProviderLoginError(f"{self.display_name} cannot determine the account login")
    # end def
# end class
