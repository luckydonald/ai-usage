"""Interactive cookie capture via a native OS webview (no bundled browser binary).

Requires the optional `pywebview` dependency (the `browser` extra) — imported lazily so the
base install doesn't need a system webview toolkit (WebKitGTK/WKWebView/WebView2) at all.
"""

from ai_usage.providers.base import ProviderError

INSTALL_HINT = (
    "Interactive browser login requires the 'browser' extra. Install it with "
    "`uv sync --extra browser` (or `pip install ai-usage[browser]`)."
)
NO_TOOLKIT_HINT = (
    "No usable GUI toolkit found for the browser login window. The 'browser' extra installs "
    "pywebview's Python bindings (PyGObject), but the native WebKitGTK (or Qt WebEngine) "
    "library itself is a system package — e.g. on Fedora: `sudo dnf install webkit2gtk4.1`, "
    "on Debian/Ubuntu: `sudo apt install gir1.2-webkit2-4.1`."
)


def capture_cookies_via_webview(url: str, title: str) -> dict[str, str]:
    """Open a native webview at `url`, let the user log in, and return cookies once they close it.

    Uses `window.get_cookies()` (not `document.cookie`) so httpOnly session cookies — which is
    what auth cookies normally are — are captured too, not just JS-readable ones.
    """
    try:
        import webview
        from webview.errors import WebViewException
    except ImportError as exception:
        raise ProviderError(INSTALL_HINT) from exception
    # end try

    captured: dict[str, str] = {}

    def on_closing() -> None:
        cookies = window.get_cookies()
        captured.update({morsel.key: morsel.value for morsel in cookies.values()})
    # end def

    window = webview.create_window(title, url)
    window.events.closing += on_closing
    try:
        webview.start()
    except WebViewException as exception:
        raise ProviderError(NO_TOOLKIT_HINT) from exception
    # end try
    return captured
# end def
