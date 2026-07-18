---
name: feedback-verify-thirdparty-return-shapes
description: "Read the actual installed third-party source for a call's return shape/threading model before relying on it — don't assume from typical conventions"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: c903d647-174d-46f2-8c61-8cf39dc278f1
  modified: 2026-07-18T22:49:00.079Z
---

When calling into a third-party library's non-obvious API (return shape, threading requirements, event semantics), read the actual installed source (`uv run python3 -c "import x, os; print(os.path.dirname(x.__file__))"` then grep/read) rather than assuming based on convention or a similar-looking stdlib API.

**Why:** Three real bugs in a row on `pywebview` integration in `ai-usage`, each only caught by the user running the real thing:
1. `webview.start()` must run on the main thread — assumed it was safe to offload via `asyncio.to_thread` like any blocking call.
2. `window.events.closing` runs its handlers synchronously *on* the GTK main thread (`should_lock=True`), while `window.events.loaded` runs them on a worker thread (`should_lock=False`) — called `get_cookies()` (which internally does `glib.idle_add` + blocking `semaphore.acquire()`) from `closing`, causing a real deadlock only reproducible by the user actually clicking close.
3. `window.get_cookies()`'s GTK backend returns `list[SimpleCookie]` (one single-entry jar per cookie), not one combined `SimpleCookie` like `http.cookies.SimpleCookie()` normally is — assumed the latter because that's what the stdlib type looks like, and pywebview's docs don't spell out the backend-specific shape.

Each of these was verifiable in under a minute by reading `webview/window.py`, `webview/event.py`, and `webview/platforms/gtk.py` directly — the fixes came from source-reading, not guessing, but only *after* a real user-reported crash prompted it.

**How to apply:** For any library wrapping a native GUI/threading model (pywebview, and likely similar for other native-binding libraries), read the source for the specific call before writing code against it — especially return shapes of "get X" methods and the threading/locking behavior of any event/callback system — rather than pattern-matching against a similarly-named stdlib type or a "typical" async convention. See also [[feedback_native_gui_needs_real_run]] for the complementary lesson (mocked tests can't catch this class of bug — real-run verification is not a substitute for reading the source, but neither replaces the other).
