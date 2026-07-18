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
# Some sites WAF-block pywebview's default (non-browser-looking) user agent. Spoofing as Safari
# rather than Chrome/V8 matters here: the underlying engine actually IS WebKit, so a Safari UA
# gets feature-detected/served content much closer to what the engine can actually render,
# whereas a Chrome UA can make sites serve Chrome-only code paths that silently fail on WebKit.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.4 Safari/605.1.15"
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
        # `get_cookies()`'s return shape differs across pywebview's backends: GTK returns a list
        # of single-entry `SimpleCookie`s, others a single `SimpleCookie` with one entry per
        # cookie — handle both rather than assuming one.
        cookies = window.get_cookies()
        jars = cookies if isinstance(cookies, list) else [cookies]
        for jar in jars:
            captured.update({morsel.key: morsel.value for morsel in jar.values()})
        # end for
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
                # some sites' CSP forbids 'unsafe-eval', which is exactly how pywebview injects
                # JS — there is no workaround via pywebview's public API. The user can still
                # click the button themselves; the window is visible to them.
                LOGGER.warning(
                    "could not auto-click %r (%s) — please click it yourself in the window.",
                    click_selector,
                    exception,
                )
            # end try
        # end if
        if state["left_initial_domain"] or current.path.rstrip("/") != initial.path.rstrip("/"):
            window.destroy()
        # end if
    # end def

    window = webview.create_window(title, url)
    window.events.loaded += on_loaded
    try:
        # debug=True enables right-click "Inspect Element" devtools, so a stuck/blank page can
        # be diagnosed (console errors, network responses) instead of guessed at blind.
        # private_mode=False: pywebview defaults to an ephemeral WebKit context, in which
        # `window.localStorage` is `undefined` rather than a normal (even if empty) Storage
        # object — modern SPAs (e.g. claude.ai) that unconditionally touch localStorage on
        # startup crash outright and never render. A normal, non-ephemeral context behaves
        # like a real browser profile here.
        webview.start(user_agent=USER_AGENT, debug=True, private_mode=False)
    except WebViewException as exception:
        raise ProviderError(NO_TOOLKIT_HINT) from exception
    # end try
    return captured
# end def
