"""Login method that captures ChatGPT session cookies via an interactive webview."""

from typing import Any

from ai_usage.providers.base import CredentialKind, LoginMethod
from ai_usage.webview_login import capture_cookies_via_webview


class CookieCaptureLogin(LoginMethod):
    key = "web-cookie-capture"
    display_name = "Sign in via browser"
    credential_kind: CredentialKind = "cookie_jar"

    login_url = "https://chatgpt.com/"
    login_button_selector = '[data-testid="login-button"]'
    # chatgpt.com's CSP forbids 'unsafe-eval', which is exactly how pywebview injects JS -- the
    # auto-click attempt (below) always fails there, so tell the user up front rather than let
    # them wonder why nothing happens.
    login_hint = "Click \"Log in\" once the page loads."

    async def authenticate(self, options: dict[str, Any]) -> dict[str, Any] | None:
        del options
        # pywebview must run on the main thread (it raises WebViewException otherwise), so this
        # is a deliberate synchronous, blocking call rather than `asyncio.to_thread(...)`.
        cookies = capture_cookies_via_webview(
            self.login_url, self.display_name, click_selector=self.login_button_selector
        )
        return {"cookies": cookies} if cookies else None
    # end def
# end class
