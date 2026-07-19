import os
import signal
import sys
import types
from http.cookies import SimpleCookie

import pytest

from ai_usage.providers.base import ProviderError
from ai_usage.webview_login import capture_cookies_via_webview


class FakeWebViewException(Exception):
    pass
# end class


class FakeEventSlot:
    def __init__(self) -> None:
        self.handlers: list = []
    # end def

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self
    # end def

    def fire(self) -> None:
        for handler in list(self.handlers):
            handler()
        # end for
    # end def
# end class


class FakeEvents:
    def __init__(self) -> None:
        self.before_load = FakeEventSlot()
        self.loaded = FakeEventSlot()
    # end def
# end class


class FakeWindow:
    def __init__(self, cookies: SimpleCookie | list[SimpleCookie], urls: list[str]) -> None:
        self.events = FakeEvents()
        self._cookies = cookies
        self._urls = urls
        self._url_index = -1
        self.destroyed = False
        self.evaluated_js: list[str] = []
        self.uid = "fake-window"
        # no `.gui` by default — `_install_click_userscript` fails gracefully and the caller
        # falls back to `evaluate_js`, matching a non-GTK backend or unexpected internals.
    # end def

    def get_cookies(self) -> SimpleCookie:
        return self._cookies
    # end def

    def get_current_url(self) -> str | None:
        return self._urls[self._url_index] if self._url_index >= 0 else None
    # end def

    def evaluate_js(self, code: str) -> None:
        self.evaluated_js.append(code)
    # end def

    def destroy(self) -> None:
        self.destroyed = True
    # end def

    def simulate_navigation(self) -> None:
        """Step through `self._urls` firing `loaded` after each, like real navigation would."""
        self.events.before_load.fire()
        for index in range(len(self._urls)):
            if self.destroyed:
                return
            # end if
            self._url_index = index
            self.events.loaded.fire()
        # end for
    # end def
# end class


def install_fake_webview(
    monkeypatch, cookies: SimpleCookie, urls: list[str] | None = None, start=None
) -> FakeWindow:
    window = FakeWindow(cookies, urls or [])

    def default_start(**kwargs) -> None:
        del kwargs
        window.simulate_navigation()
    # end def

    fake_module = types.SimpleNamespace(
        create_window=lambda title, url: window,
        start=start or default_start,
    )
    fake_errors_module = types.SimpleNamespace(WebViewException=FakeWebViewException)
    monkeypatch.setitem(sys.modules, "webview", fake_module)
    monkeypatch.setitem(sys.modules, "webview.errors", fake_errors_module)
    return window
# end def


def test_capture_cookies_via_webview_snapshots_cookies_on_every_load(monkeypatch) -> None:
    cookies = SimpleCookie()
    cookies["session"] = "abc123"
    window = install_fake_webview(
        monkeypatch, cookies, urls=["https://example.test/login"]
    )

    result = capture_cookies_via_webview("https://example.test/login", "Example")

    assert result == {"session": "abc123"}
    assert not window.destroyed
# end def


def test_capture_cookies_via_webview_handles_gtk_style_list_of_single_entry_cookies(
    monkeypatch,
) -> None:
    session = SimpleCookie()
    session["session"] = "abc"
    theme = SimpleCookie()
    theme["theme"] = "dark"
    install_fake_webview(monkeypatch, [session, theme], urls=["https://example.test/login"])

    result = capture_cookies_via_webview("https://example.test/login", "Example")

    assert result == {"session": "abc", "theme": "dark"}
# end def


def test_capture_cookies_via_webview_returns_empty_dict_without_cookies(monkeypatch) -> None:
    install_fake_webview(monkeypatch, [], urls=["https://example.test/login"])

    result = capture_cookies_via_webview("https://example.test/login", "Example")

    assert result == {}
# end def


def test_capture_cookies_via_webview_detects_same_domain_path_change(monkeypatch) -> None:
    cookies = SimpleCookie()
    cookies["session"] = "claude-session"
    window = install_fake_webview(
        monkeypatch,
        cookies,
        urls=["https://claude.ai/login", "https://claude.ai/new"],
    )

    result = capture_cookies_via_webview("https://claude.ai/login", "Claude")

    assert result == {"session": "claude-session"}
    assert window.destroyed
# end def


def test_capture_cookies_via_webview_does_not_close_on_same_page_reload(monkeypatch) -> None:
    cookies = SimpleCookie()
    cookies["session"] = "still-on-login"
    window = install_fake_webview(
        monkeypatch,
        cookies,
        urls=["https://claude.ai/login", "https://claude.ai/login"],
    )

    result = capture_cookies_via_webview("https://claude.ai/login", "Claude")

    # never navigated away from /login — cookies are still captured (snapshotted every load),
    # just never auto-closed
    assert result == {"session": "still-on-login"}
    assert not window.destroyed
# end def


def test_capture_cookies_via_webview_detects_cross_domain_round_trip_and_clicks_button(
    monkeypatch,
) -> None:
    cookies = SimpleCookie()
    cookies["session"] = "chatgpt-session"
    window = install_fake_webview(
        monkeypatch,
        cookies,
        urls=[
            "https://chatgpt.com/",
            "https://auth.openai.com/login",
            "https://chatgpt.com/",
        ],
    )

    result = capture_cookies_via_webview(
        "https://chatgpt.com/", "Codex", click_selector='[data-testid="login-button"]'
    )

    assert result == {"session": "chatgpt-session"}
    assert window.destroyed
    assert window.evaluated_js == [
        'document.querySelector(\'[data-testid="login-button"]\')?.click();'
    ]
# end def


def test_capture_cookies_via_webview_prefers_the_userscript_click_when_gtk_internals_exist(
    monkeypatch,
) -> None:
    cookies = SimpleCookie()
    cookies["session"] = "chatgpt-session"
    window = install_fake_webview(
        monkeypatch,
        cookies,
        urls=[
            "https://chatgpt.com/",
            "https://auth.openai.com/login",
            "https://chatgpt.com/",
        ],
    )

    added_scripts: list[str] = []

    class FakeManager:
        def add_script(self, script) -> None:
            added_scripts.append(script)
        # end def
    # end class

    class FakeBrowser:
        manager = FakeManager()
    # end class

    class FakeInstances:
        def get(self, uid):
            return FakeBrowser() if uid == window.uid else None
        # end def
    # end class

    class FakeBrowserView:
        instances = FakeInstances()
    # end class

    window.gui = types.SimpleNamespace(BrowserView=FakeBrowserView)

    fake_webkit2 = types.SimpleNamespace(
        UserScript=lambda source, injected_frames, injection_time, allow_list, block_list: source,
        UserContentInjectedFrames=types.SimpleNamespace(TOP_FRAME="top-frame"),
        UserScriptInjectionTime=types.SimpleNamespace(END="end"),
    )
    monkeypatch.setitem(sys.modules, "gi", types.SimpleNamespace(require_version=lambda *a: None))
    monkeypatch.setitem(sys.modules, "gi.repository", types.SimpleNamespace(WebKit2=fake_webkit2))

    result = capture_cookies_via_webview(
        "https://chatgpt.com/", "Codex", click_selector='[data-testid="login-button"]'
    )

    assert result == {"session": "chatgpt-session"}
    assert len(added_scripts) == 1
    assert window.evaluated_js == []  # the evaluate_js fallback should never be reached
# end def


def test_capture_cookies_via_webview_tolerates_a_blocked_click(monkeypatch) -> None:
    cookies = SimpleCookie()
    cookies["session"] = "clicked-anyway"
    window = install_fake_webview(
        monkeypatch, cookies, urls=["https://chatgpt.com/", "https://chatgpt.com/chat"]
    )

    def raise_js_exception(code: str) -> None:
        raise RuntimeError("CSP blocked eval")
    # end def

    window.evaluate_js = raise_js_exception

    result = capture_cookies_via_webview(
        "https://chatgpt.com/", "Codex", click_selector='[data-testid="login-button"]'
    )

    assert result == {"session": "clicked-anyway"}
    assert window.destroyed
# end def


def test_capture_cookies_via_webview_closes_the_window_on_sigint(monkeypatch) -> None:
    cookies = SimpleCookie()
    cookies["session"] = "abc123"
    window = install_fake_webview(monkeypatch, cookies, urls=["https://example.test/login"])
    original_handler = signal.getsignal(signal.SIGINT)

    def start_and_send_sigint(**kwargs) -> None:
        del kwargs
        window.simulate_navigation()
        os.kill(os.getpid(), signal.SIGINT)
    # end def

    monkeypatch.setattr(sys.modules["webview"], "start", start_and_send_sigint)

    result = capture_cookies_via_webview("https://example.test/login", "Example")

    assert result == {"session": "abc123"}
    assert window.destroyed
    assert signal.getsignal(signal.SIGINT) is original_handler
# end def


def test_capture_cookies_via_webview_only_destroys_the_window_once(monkeypatch) -> None:
    # Regression test for a real crash: `window.destroy()` used to be called from both the
    # navigation-triggered auto-close (on_loaded, background thread) and a SIGINT arriving around
    # the same time (main thread) with no guard — a double-destroy that corrupted GTK's native
    # state (`free(): corrupted unsorted chunks`). Simulates both firing for the same window.
    cookies = SimpleCookie()
    cookies["session"] = "abc123"
    window = install_fake_webview(
        monkeypatch, cookies, urls=["https://claude.ai/login", "https://claude.ai/new"]
    )
    destroy_calls: list[None] = []
    real_destroy = window.destroy

    def counting_destroy() -> None:
        destroy_calls.append(None)
        real_destroy()
    # end def

    window.destroy = counting_destroy

    def start_with_redundant_sigint(**kwargs) -> None:
        del kwargs
        window.simulate_navigation()  # path changes claude.ai/login -> /new: auto-destroys once
        os.kill(os.getpid(), signal.SIGINT)  # redundant second attempt right after
    # end def

    monkeypatch.setattr(sys.modules["webview"], "start", start_with_redundant_sigint)

    result = capture_cookies_via_webview("https://claude.ai/login", "Claude")

    assert result == {"session": "abc123"}
    assert len(destroy_calls) == 1
# end def


def test_capture_cookies_via_webview_raises_a_clear_error_when_pywebview_is_missing(
    monkeypatch,
) -> None:
    monkeypatch.setitem(sys.modules, "webview", None)
    monkeypatch.setitem(sys.modules, "webview.errors", None)

    with pytest.raises(ProviderError, match="browser' extra"):
        capture_cookies_via_webview("https://example.test/login", "Example")
    # end with
# end def


def test_capture_cookies_via_webview_raises_a_clear_error_without_a_gui_toolkit(
    monkeypatch,
) -> None:
    def raise_no_toolkit(**kwargs) -> None:
        del kwargs
        raise FakeWebViewException("You must have either QT or GTK...")
    # end def

    install_fake_webview(monkeypatch, SimpleCookie(), start=raise_no_toolkit)

    with pytest.raises(ProviderError, match="WebKitGTK"):
        capture_cookies_via_webview("https://example.test/login", "Example")
    # end with
# end def
