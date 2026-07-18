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
# end class


class FakeEvents:
    def __init__(self) -> None:
        self.closing = FakeEventSlot()
    # end def
# end class


class FakeWindow:
    def __init__(self, cookies: SimpleCookie) -> None:
        self.events = FakeEvents()
        self._cookies = cookies
    # end def

    def get_cookies(self) -> SimpleCookie:
        return self._cookies
    # end def
# end class


def install_fake_webview(monkeypatch, cookies: SimpleCookie, start=None) -> FakeWindow:
    window = FakeWindow(cookies)
    fake_module = types.SimpleNamespace(
        create_window=lambda title, url: window,
        start=start or (lambda: [handler() for handler in window.events.closing.handlers]),
    )
    fake_errors_module = types.SimpleNamespace(WebViewException=FakeWebViewException)
    monkeypatch.setitem(sys.modules, "webview", fake_module)
    monkeypatch.setitem(sys.modules, "webview.errors", fake_errors_module)
    return window
# end def


def test_capture_cookies_via_webview_returns_cookies_after_close(monkeypatch) -> None:
    cookies = SimpleCookie()
    cookies["session"] = "abc123"
    install_fake_webview(monkeypatch, cookies)

    result = capture_cookies_via_webview("https://example.test/login", "Example")

    assert result == {"session": "abc123"}
# end def


def test_capture_cookies_via_webview_returns_empty_dict_without_cookies(monkeypatch) -> None:
    install_fake_webview(monkeypatch, SimpleCookie())

    result = capture_cookies_via_webview("https://example.test/login", "Example")

    assert result == {}
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
    def raise_no_toolkit() -> None:
        raise FakeWebViewException("You must have either QT or GTK...")
    # end def

    install_fake_webview(monkeypatch, SimpleCookie(), start=raise_no_toolkit)

    with pytest.raises(ProviderError, match="WebKitGTK"):
        capture_cookies_via_webview("https://example.test/login", "Example")
    # end with
# end def
