"""Kimi (Moonshot) provider: OAuth device-flow login + coding/v1/usages endpoint.

`user_identity()` always raises: no email/username/JWT claim exists anywhere in Kimi's
OAuth or usage flow (confirmed against the reference plugin's source), so `provider add`
will always fail at the verify step until identity handling changes elsewhere. This is a
known, accepted limitation — not a bug — per explicit product decision.
"""

from ai_usage.models import AccountConfig, ProviderFetchResult
from ai_usage.providers.base import Provider, ProviderLoginError
from ai_usage.providers.kimi.login.web.device_flow_login import DeviceFlowLogin
from ai_usage.providers.kimi.usage.web.usages_api import UsagesApiUsage


class KimiUsageProvider(Provider):
    service = "kimi"
    key = "web"
    display_name = "Kimi (Moonshot) coding usage"
    login_url = "https://auth.kimi.com/api/oauth/device_authorization"
    usage_method = UsagesApiUsage()
    login_methods = (DeviceFlowLogin(),)

    def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
        del account, result
        raise ProviderLoginError(f"{self.display_name} could not determine the account login")
    # end def
# end class
