"""OpenRouter provider: static provisioning key + credits/activity endpoints."""

from ai_usage.models import AccountConfig, ProviderFetchResult
from ai_usage.providers._shared.static_api_key import StaticApiKeyLogin
from ai_usage.providers.base import Provider, ProviderLoginError
from ai_usage.providers.openrouter.usage.web.private_api import OpenRouterUsage


class OpenRouterProvider(Provider):
    service = "openrouter"
    key = "api"
    display_name = "OpenRouter credits"
    usage_method = OpenRouterUsage()
    login_methods = (StaticApiKeyLogin(display_name="OpenRouter provisioning key"),)

    def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
        # Neither /api/v1/credits nor /api/v1/activity expose any account identity field.
        del account, result
        raise ProviderLoginError(f"{self.display_name} could not determine the account login")
    # end def
# end class
