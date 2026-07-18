---
name: feedback-native-gui-needs-real-run
description: "pywebview/native-GUI code needs a real, non-mocked CLI run (via `script` for a genuine tty) — mocked unit tests can't catch main-thread or missing-toolkit failures"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: c903d647-174d-46f2-8c61-8cf39dc278f1
  modified: 2026-07-18T21:00:36.617Z
---

For code driving a native GUI toolkit (pywebview here, likely similar for any GTK/Qt/native webview integration), unit tests that mock the library at the module boundary (`sys.modules["webview"] = fake`) cannot catch real integration failures — thread-affinity requirements, missing native libraries, or missing Python bindings all only show up when the real library actually runs.

**Why:** Shipped `webview_login.py`'s `capture_cookies_via_webview()` twice with mocked-only test coverage, and it crashed for the user both times on first real use: first `WebViewException('pywebview must be run on a main thread.')` (fixed by dropping `asyncio.to_thread`), then immediately after, `WebViewException: You must have either QT or GTK with Python extensions installed` (needed `pygobject` added to the `browser` extra, plus a system WebKitGTK library the extra can't install). The user had to paste two separate real tracebacks before either surfaced — a mocked test suite gave false confidence both times.

**How to apply:** After writing/changing code that drives pywebview (or similar native-GUI libraries), actually run the real CLI command through a genuine pty — `script -qec "timeout <n> <command>" /tmp/out.log` works well in this sandboxed environment where a plain shell redirect isn't a tty and `interactive_terminal()`-style checks silently no-op. A `timeout`-truncated run that reaches the blocking native call (rather than crashing before it) is a meaningful, cheap smoke test — don't rely solely on mocked unit tests for this class of bug.
