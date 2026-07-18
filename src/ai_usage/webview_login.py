"""Interactive cookie capture via a native OS webview (no bundled browser binary).

Requires the optional `pywebview` dependency (the `browser` extra) — imported lazily so the
base install doesn't need a system webview toolkit (WebKitGTK/WKWebView/WebView2) at all.
"""

import logging
from urllib.parse import urlsplit

from ai_usage.providers.base import ProviderError

LOGGER = logging.getLogger(__name__)

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
# Some sites WAF-block pywebview's default (non-browser-looking) user agent. Presenting as a
# normal desktop Chrome avoids that without changing anything about the actual login flow.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)


def capture_cookies_via_webview(
    url: str, title: str, click_selector: str | None = None
) -> dict[str, str]:
    """Open a native webview at `url`, let the user log in, and return cookies once logged in.

    `url` should be the site's actual login page (or homepage, with `click_selector` pointing at
    its login button) — not an API endpoint; API endpoints often reject direct browser navigation.

    Cookies are snapshotted on every page load while still on `url`'s domain (safe: `loaded`
    handlers run off the main thread) rather than when the window closes — `get_cookies()` uses a
    blocking main-thread round trip internally, which would deadlock GTK's close handler (`closing`
    handlers run *on* the main thread) if called from there. So by the time the window closes for
    any reason — the login-detection heuristic below, or the user closing it manually — the latest
    snapshot is already captured; `closing` itself does no work.

    Login is detected from navigation alone (no need to close the window): either the browser
    briefly left `url`'s domain (an SSO/OAuth hop) and came back, or it stayed on the same domain
    but moved off the initial path (e.g. `/login` -> `/`).
    """
    try:
        import webview
        from webview.errors import WebViewException
    except ImportError as exception:
        raise ProviderError(INSTALL_HINT) from exception
    # end try

    initial = urlsplit(url)
    state = {"left_initial_domain": False, "clicked": False}
    captured: dict[str, str] = {}

    def snapshot_cookies() -> None:
        cookies = window.get_cookies()
        captured.update({morsel.key: morsel.value for morsel in cookies.values()})
    # end def

    def on_loaded() -> None:
        current = urlsplit(window.get_current_url() or "")
        if current.netloc != initial.netloc:
            state["left_initial_domain"] = True
            return
        # end if
        snapshot_cookies()
        if click_selector and not state["clicked"]:
            state["clicked"] = True
            try:
                window.evaluate_js(f"document.querySelector({click_selector!r})?.click();")
            except Exception as exception:  # noqa: BLE001
                # some sites' CSP blocks eval-based JS injection entirely — the user can still
                # click the button themselves, the window is visible to them.
                LOGGER.debug("could not auto-click %r: %s", click_selector, exception)
            # end try
        # end if
        if state["left_initial_domain"] or current.path.rstrip("/") != initial.path.rstrip("/"):
            window.destroy()
        # end if
    # end def

    window = webview.create_window(title, url)
    window.events.loaded += on_loaded
    try:
        webview.start(user_agent=USER_AGENT)
    except WebViewException as exception:
        raise ProviderError(NO_TOOLKIT_HINT) from exception
    # end try
    return captured
# end def
