---
name: feedback-native-gui-needs-real-run
description: "pywebview/native-GUI code needs a real, non-mocked CLI run (via `script` for a genuine tty) — mocked unit tests can't catch main-thread or missing-toolkit failures"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: c903d647-174d-46f2-8c61-8cf39dc278f1
  modified: 2026-07-18T21:00:36.617Z
---
Code driving native GUI toolkit (pywebview here, likely similar any GTK/Qt/native webview integration): unit tests mock library at module boundary (`sys.modules["webview"] = fake`) — can't catch real integration failures. Thread-affinity requirements, missing native libraries, missing Python bindings only show up when real library actually runs.

**Why:** Shipped `webview_login.py`'s `capture_cookies_via_webview()` twice with mocked-only test coverage. Crashed for user both times on first real use: first `WebViewException('pywebview must be run on a main thread.')` (fixed by dropping `asyncio.to_thread`), then immediately after, `WebViewException: You must have either QT or GTK with Python extensions installed` (needed `pygobject` added to `browser` extra, plus system WebKitGTK library extra can't install). User had to paste two separate real tracebacks before either surfaced — mocked test suite gave false confidence both times.

**How to apply:** After writing/changing code driving pywebview (or similar native-GUI libraries), actually run real CLI command through genuine pty — `script -qec "timeout <n> <command>" /tmp/out.log` works well in this sandboxed environment where plain shell redirect isn't tty and `interactive_terminal()`-style checks silently no-op. A `timeout`-truncated run that reaches blocking native call (rather than crashing before it) = meaningful, cheap smoke test. Don't rely solely on mocked unit tests for this bug class.
