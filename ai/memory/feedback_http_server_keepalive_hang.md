---
name: feedback-http-server-keepalive-hang
description: A local http.server.BaseHTTPRequestHandler response without Content-Length hangs HTTP/1.1 keep-alive clients indefinitely
metadata: 
  node_type: memory
  type: feedback
  originSessionId: ae3f5d59-bf5b-4a03-9fa5-5f15e5d1e6b3
  modified: 2026-07-26T06:28:15.855Z
---

Any hand-rolled `http.server.BaseHTTPRequestHandler.do_GET`/`do_POST` used as a local loopback listener (e.g. an OAuth authorization-code callback catcher) must send an explicit `Content-Length` header — and ideally `Connection: close` + `self.close_connection = True` — or an HTTP/1.1 client (like `httpx.AsyncClient`) will hang forever waiting for more body bytes it can never determine the end of.

**Why:** Root-caused a real hang in `ai-usage`'s new PKCE-login shared helper (`src/ai_usage/providers/_shared/oauth_pkce.py`) this way — the callback handler wrote a response body but never set `Content-Length`, so the test's `httpx.AsyncClient.get()` to the loopback URL blocked indefinitely under keep-alive. Fixed by adding `Content-Length` + `Connection: close` + `close_connection = True` to the handler.

**How to apply:** Whenever writing or reviewing a local `http.server`-based callback listener (device-flow, PKCE, or any "catch this one redirect" pattern), check the response explicitly sets `Content-Length` (or a chunked-encoding header) before assuming the design is correct — a hang here looks exactly like a deadlock in the caller's queue/thread logic, not a missing HTTP header.
