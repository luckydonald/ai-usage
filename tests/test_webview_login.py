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
