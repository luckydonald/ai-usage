"""Interactive cookie capture via a native OS webview (no bundled browser binary).

Requires the optional `pywebview` dependency (the `browser` extra) — imported lazily so the
base install doesn't need a system webview toolkit (WebKitGTK/WKWebView/WebView2) at all.
"""

import logging
import signal
import threading
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


def _click_script(selector: str) -> str:
    return f"""
(function() {{
    function tryClick() {{
        var el = document.querySelector({selector!r});
        if (el) {{ el.click(); return true; }}
        return false;
    }}
    if (!tryClick()) {{
        var observer = new MutationObserver(function() {{
            if (tryClick()) observer.disconnect();
        }});
        observer.observe(document.documentElement, {{childList: true, subtree: true}});
    }}
}})();
"""
# end def


def _install_click_userscript(window, selector: str) -> bool:
    """Best-effort: inject the click as a WebKit *user script* rather than `evaluate_js`.

    User scripts (the mechanism real browser extensions use for content scripts) run outside the
    page's own JS world and aren't subject to its CSP — unlike `evaluate_js`/`run_js`, which both
    execute via WebKit's `evaluate_javascript()` in the page's main world and get blocked by a
    'unsafe-eval'-forbidding CSP every time. This reaches into pywebview's private GTK internals
    (`window.gui` is the `platforms.gtk` module; `BrowserView.instances[uid]` is the per-window
    native object holding the `WebKitUserContentManager`), so it's fragile across pywebview
    versions and only works on the GTK backend. Returns False (caller should fall back to
    `evaluate_js`) if any of that isn't available.
    """
    try:
        import gi

        gi.require_version("WebKit2", "4.1")
        from gi.repository import WebKit2

        browser = window.gui.BrowserView.instances.get(window.uid)
        if browser is None:
            return False
        # end if
        script = WebKit2.UserScript(
            _click_script(selector),
            WebKit2.UserContentInjectedFrames.TOP_FRAME,
            WebKit2.UserScriptInjectionTime.END,
            None,
            None,
        )
        browser.manager.add_script(script)
        return True
    except Exception as exception:  # noqa: BLE001
        LOGGER.debug("could not install click user-script: %s", exception)
        return False
    # end try
# end def


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
    state = {"left_initial_domain": False, "clicked": False, "userscript_installed": False}
    captured: dict[str, str] = {}
    destroy_lock = threading.Lock()
    destroyed = {"value": False}

    def destroy_once() -> None:
        # `window.destroy()` is called both from `on_loaded` (a background thread — pywebview's
        # `loaded` event isn't main-thread-locked) and from the SIGINT handler (the main thread,
        # whenever Python regains control). Without this guard, both can race and call it at
        # nearly the same instant, double-destroying the underlying GTK widget — this reliably
        # reproduced as `free(): corrupted unsorted chunks`, a native heap-corruption crash.
        with destroy_lock:
            if destroyed["value"]:
                return
            # end if
            destroyed["value"] = True
            window.destroy()
        # end with
    # end def

    def on_before_load() -> None:
        if click_selector:
            state["userscript_installed"] = _install_click_userscript(window, click_selector)
        # end if
    # end def

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
        if click_selector and not state["clicked"] and not state["userscript_installed"]:
            state["clicked"] = True
            try:
                window.evaluate_js(f"document.querySelector({click_selector!r})?.click();")
            except Exception as exception:  # noqa: BLE001
                # some sites' CSP forbids 'unsafe-eval', which is exactly how pywebview's
                # evaluate_js/run_js inject code — the user-script path above (installed on
                # `before_load`) is the workaround; this is only reached when that didn't apply.
                # The user can still click the button themselves; the window is visible to them.
                LOGGER.warning(
                    "could not auto-click %r (%s) — please click it yourself in the window.",
                    click_selector,
                    exception,
                )
            # end try
        # end if
        if state["left_initial_domain"] or current.path.rstrip("/") != initial.path.rstrip("/"):
            destroy_once()
        # end if
    # end def

    window = webview.create_window(title, url)
    window.events.before_load += on_before_load
    window.events.loaded += on_loaded

    def handle_sigint(signum, frame) -> None:
        # webview.start() blocks in GTK's C-level main loop, which doesn't return control to
        # Python's interpreter (and thus its signal handling) between iterations quickly — the
        # default asyncio SIGINT handler just raises KeyboardInterrupt repeatedly with no effect.
        # Closing the window directly from here actually breaks the loop.
        del signum, frame
        destroy_once()
    # end def

    previous_handler = signal.signal(signal.SIGINT, handle_sigint)
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
    finally:
        signal.signal(signal.SIGINT, previous_handler)
    # end try
    # print(), not LOGGER.warning(): logging output from this function is unreliable — it went
    # missing under `debug=True` in live testing despite working in isolation (root cause not yet
    # found; low priority next to the Cloudflare-fingerprint finding below).
    print(f"[ai-usage] captured {len(captured)} cookie(s): {', '.join(sorted(captured))}")
    return captured
# end def
