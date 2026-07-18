"""Interactive cookie capture via a native OS webview (no bundled browser binary).

Requires the optional `pywebview` dependency (the `browser` extra) — imported lazily so the
base install doesn't need a system webview toolkit (WebKitGTK/WKWebView/WebView2) at all.
"""

from urllib.parse import urlsplit

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


def capture_cookies_via_webview(
    url: str, title: str, click_selector: str | None = None
) -> dict[str, str]:
    """Open a native webview at `url`, let the user log in, and return cookies once logged in.

    `url` should be the site's actual login page (or homepage, with `click_selector` pointing at
    its login button) — not an API endpoint; API endpoints often reject direct browser navigation.

    Detects a successful login from navigation alone (no need for the user to close the window):
    either the browser briefly left `url`'s domain (an SSO/OAuth hop) and came back, or it stayed
    on the same domain but moved off the initial path (e.g. `/login` -> `/`). Falls back to
    capturing cookies when the user closes the window themselves, in case that heuristic doesn't
    fire (already logged in, unusual redirect chain, etc).

    Uses `window.get_cookies()` (not `document.cookie`) so httpOnly session cookies — which is
    what auth cookies normally are — are captured too, not just JS-readable ones.
    """
    try:
        import webview
        from webview.errors import WebViewException
    except ImportError as exception:
        raise ProviderError(INSTALL_HINT) from exception
    # end try

    initial = urlsplit(url)
    state = {"left_initial_domain": False, "clicked": False, "done": False}
    captured: dict[str, str] = {}

    def grab_cookies() -> None:
        cookies = window.get_cookies()
        captured.update({morsel.key: morsel.value for morsel in cookies.values()})
    # end def

    def grab_and_close() -> None:
        if state["done"]:
            return
        # end if
        state["done"] = True
        grab_cookies()
        window.destroy()
    # end def

    def on_closing() -> None:
        if not state["done"]:
            grab_cookies()
        # end if
    # end def

    def on_loaded() -> None:
        current = urlsplit(window.get_current_url() or "")
        if click_selector and not state["clicked"] and current.netloc == initial.netloc:
            window.evaluate_js(f"document.querySelector({click_selector!r})?.click();")
            state["clicked"] = True
            return
        # end if
        if current.netloc != initial.netloc:
            state["left_initial_domain"] = True
            return
        # end if
        if state["left_initial_domain"] or current.path.rstrip("/") != initial.path.rstrip("/"):
            grab_and_close()
        # end if
    # end def

    window = webview.create_window(title, url)
    window.events.closing += on_closing
    window.events.loaded += on_loaded
    try:
        webview.start()
    except WebViewException as exception:
        raise ProviderError(NO_TOOLKIT_HINT) from exception
    # end try
    return captured
# end def
