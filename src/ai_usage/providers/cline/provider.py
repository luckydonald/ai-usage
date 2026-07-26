"""Cline provider: static API key + api.cline.bot balance/usage endpoints."""

from ai_usage.models import AccountConfig, ProviderFetchResult
from ai_usage.providers._shared.static_api_key import StaticApiKeyLogin
from ai_usage.providers.base import Provider, canonical_login
from ai_usage.providers.cline.usage.web.private_api import ClineUsage


class ClineProvider(Provider):
    service = "cline"
    key = "api"
    display_name = "Cline usage"
    usage_method = ClineUsage()
    login_methods = (StaticApiKeyLogin(display_name="Cline API key"),)

    def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
        del account
        return canonical_login(result.identity.name if result.identity else None, self.display_name)
    # end def
# end class
