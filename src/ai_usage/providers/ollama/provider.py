"""Ollama Cloud provider: cookie-jar login + HTML-scraped settings page."""

from ai_usage.models import AccountConfig, ProviderFetchResult
from ai_usage.providers.base import Provider, ProviderLoginError
from ai_usage.providers.ollama.login.web.cookie_capture import CookieCaptureLogin
from ai_usage.providers.ollama.usage.web.settings_scrape import SettingsScrapeUsage


class OllamaCloudUsageProvider(Provider):
    service = "ollama"
    key = "web"
    display_name = "Ollama Cloud usage"
    login_url = "https://ollama.com"
    usage_method = SettingsScrapeUsage()
    login_methods = (CookieCaptureLogin(),)

    def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
        # ollama.com/settings does not expose an email/username element in the scraped section.
        del account, result
        raise ProviderLoginError(f"{self.display_name} could not determine the account login")
    # end def
# end class
