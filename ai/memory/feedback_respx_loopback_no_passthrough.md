---
name: feedback-respx-loopback-no-passthrough
description: "respx's assert_all_mocked=False / route(...).pass_through() does not reliably proxy to a real local loopback HTTP server in this environment"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: ae3f5d59-bf5b-4a03-9fa5-5f15e5d1e6b3
  modified: 2026-07-26T06:28:07.667Z
---

When testing code that runs a real local `http.server` (e.g. an OAuth loopback callback listener) alongside `respx.mock`, respx's `assert_all_mocked=False` and `respx.route(host="127.0.0.1").pass_through()` do NOT reliably forward the request to the real local server — they were observed returning a synthetic empty 200 instead, silently swallowing the request. This caused an indefinite hang (`queue.Queue.get(timeout=...)` never receiving the callback) that looked like a bug in the code under test but was actually a test-harness limitation.

**Why:** Confirmed by isolating the exact scenario in a standalone script outside pytest — a plain local `http.server` returning `b"hello"` came back as an empty string body under `@respx.mock(assert_all_mocked=False)` even with an explicit `pass_through()` route, while the same call worked instantly outside any respx context.

**How to apply:** When a test needs to exercise a real local socket server (loopback OAuth callbacks, local relay files, etc.) *and* also mock an external HTTP endpoint (like a token-exchange POST) in the same test, don't rely on respx for the loopback leg. Either avoid the `@respx.mock` decorator entirely for that test and monkeypatch the specific outbound call directly (e.g. `monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)`), or run the loopback-server assertions in a separate test with no respx involved. See [[project_ai_usage_provider_add_wizard]] for the provider architecture this came up in (SuperGrok's PKCE login test, `tests/test_oauth_pkce.py`).
