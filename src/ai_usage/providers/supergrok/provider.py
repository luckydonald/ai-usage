"""SuperGrok (xAI) provider: OAuth PKCE login + cli-chat-proxy.grok.com billing API."""

from ai_usage.models import AccountConfig, ProviderFetchResult
from ai_usage.providers.base import Provider, ProviderLoginError, canonical_login
from ai_usage.providers.supergrok.login.web.pkce_login import PkceLogin
from ai_usage.providers.supergrok.usage.web.billing_api import BillingApiUsage


class SuperGrokBillingProvider(Provider):
    service = "supergrok"
    key = "web"
    display_name = "SuperGrok (xAI) billing"
    login_url = "https://auth.x.ai/oauth2/authorize"
    usage_method = BillingApiUsage()
    login_methods = (PkceLogin(),)

    def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
        del account
        if result.identity and (result.identity.email or result.identity.name):
            return canonical_login(result.identity.email or result.identity.name, self.display_name)
        # end if
        # xAI's billing/settings endpoints expose no identity; only the OAuth id_token's
        # email/sub claim (decoded best-effort in PkceLogin) can supply one.
        raise ProviderLoginError(f"{self.display_name} could not determine the account login")
    # end def
# end class
