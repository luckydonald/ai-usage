---
name: feedback-verify-thirdparty-return-shapes
description: "Read the actual installed third-party source for a call's return shape/threading model before relying on it — don't assume from typical conventions"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: c903d647-174d-46f2-8c61-8cf39dc278f1
  modified: 2026-07-18T22:49:00.079Z
---
Third-party lib API non-obvious (return shape, threading, event semantics)? Read installed source (`uv run python3 -c "import x, os; print(os.path.dirname(x.__file__))"` then grep/read), don't assume from convention or similar stdlib API.

**Why:** Three real bugs, `pywebview` integration in `ai-usage`, each caught only by user running real thing:
1. `webview.start()` must run main thread — assumed safe offload via `asyncio.to_thread` like normal blocking call.
2. `window.events.closing` handlers run synchronously on GTK main thread (`should_lock=True`); `window.events.loaded` handlers run worker thread (`should_lock=False`) — called `get_cookies()` (does `glib.idle_add` + blocking `semaphore.acquire()`) from `closing`, real deadlock, only reproducible by user clicking close.
3. `window.get_cookies()` GTK backend returns `list[SimpleCookie]` (one single-entry jar per cookie), not one combined `SimpleCookie` like stdlib `http.cookies.SimpleCookie()` — assumed stdlib shape, pywebview docs don't spell out backend-specific shape.

Each verifiable under a minute reading `webview/window.py`, `webview/event.py`, `webview/platforms/gtk.py` directly — fixes came from source-reading not guessing, but only after real user-reported crash prompted it.

**How to apply:** Any lib wrapping native GUI/threading model (pywebview, similar native-binding libs) — read source for specific call before coding against it, especially "get X" method return shapes and event/callback threading/locking behavior, rather than pattern-match against similarly-named stdlib type or "typical" async convention. See also [[feedback_native_gui_needs_real_run]] — complementary lesson: mocked tests can't catch this bug class, real-run verification doesn't substitute source-reading, neither replaces other.
