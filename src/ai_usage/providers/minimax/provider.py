"""MiniMax provider: static API key + region-selected coding_plan/remains endpoint."""

from ai_usage.models import AccountConfig, ProviderFetchResult
from ai_usage.providers._shared.static_api_key import StaticApiKeyLogin
from ai_usage.providers.base import ConfigurationField, Provider, ProviderLoginError
from ai_usage.providers.minimax.usage.web.private_api import MiniMaxUsage


class MiniMaxProvider(Provider):
    service = "minimax"
    key = "api"
    display_name = "MiniMax coding plan"
    configuration_fields = (
        ConfigurationField(
            key="region", label="Region (global or cn)", required=True, default="global"
        ),
    )
    usage_method = MiniMaxUsage()
    login_methods = (StaticApiKeyLogin(display_name="MiniMax API key"),)

    def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
        # MiniMax's coding_plan/remains payload has no email/username field.
        del account, result
        raise ProviderLoginError(f"{self.display_name} could not determine the account login")
    # end def
# end class
