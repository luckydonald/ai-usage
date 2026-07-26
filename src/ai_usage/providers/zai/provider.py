"""Z.ai provider: static API key + subscription/quota-limit JSON endpoints."""

from ai_usage.models import AccountConfig, ProviderFetchResult
from ai_usage.providers._shared.static_api_key import StaticApiKeyLogin
from ai_usage.providers.base import Provider, ProviderLoginError
from ai_usage.providers.zai.usage.web.private_api import ZaiUsage


class ZaiProvider(Provider):
    service = "zai"
    key = "api"
    display_name = "Z.ai coding plan"
    usage_method = ZaiUsage()
    login_methods = (StaticApiKeyLogin(display_name="Z.ai API key"),)

    def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
        # Neither Z.ai endpoint this provider calls exposes an email/username — the
        # subscription/quota payloads only carry plan- and limit-level data, nothing that
        # identifies the account itself.
        del account, result
        raise ProviderLoginError(f"{self.display_name} could not determine the account login")
    # end def
# end class
