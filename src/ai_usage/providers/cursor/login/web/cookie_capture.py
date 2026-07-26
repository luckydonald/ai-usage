"""Browser cookie-capture login for Cursor (WorkosCursorSessionToken)."""

from typing import Any

from ai_usage.providers.base import LoginMethod
from ai_usage.webview_login import capture_cookies_via_webview

CURSOR_LOGIN_URL = "https://cursor.com/login"


class CookieCaptureLogin(LoginMethod):
    key = "cookie_capture"
    display_name = "Sign in via browser"
    credential_kind = "cookie_jar"

    async def authenticate(self, options: dict[str, Any]) -> dict[str, Any] | None:
        del options
        # pywebview must run on the main thread — see Claude's CookieCaptureLogin for details.
        cookies = capture_cookies_via_webview(CURSOR_LOGIN_URL, self.display_name)
        return {"cookies": cookies} if cookies else None
    # end def
# end class
