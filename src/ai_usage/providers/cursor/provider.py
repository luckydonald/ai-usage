"""Cursor provider: cookie-jar login + REST-then-gRPC-JSON usage fallback."""

from ai_usage.models import AccountConfig, ProviderFetchResult
from ai_usage.providers.base import (
    FallbackUsageMethod,
    Provider,
    ProviderLoginError,
    canonical_login,
)
from ai_usage.providers.cursor.login.web.cookie_capture import CookieCaptureLogin
from ai_usage.providers.cursor.usage.web.grpc_json import GrpcJsonUsage
from ai_usage.providers.cursor.usage.web.private_api import PrivateApiUsage


class CursorUsageProvider(Provider):
    service = "cursor"
    key = "web"
    display_name = "Cursor usage"
    login_url = "https://cursor.com/login"
    usage_method = FallbackUsageMethod((PrivateApiUsage(), GrpcJsonUsage()))
    login_methods = (CookieCaptureLogin(),)

    def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
        del account
        if result.identity and (result.identity.email or result.identity.name):
            return canonical_login(result.identity.email or result.identity.name, self.display_name)
        # end if
        raise ProviderLoginError(f"{self.display_name} could not determine the account login")
    # end def
# end class
