---
name: project-cloudflare-tls-fingerprint-codex
description: "chatgpt.com AND claude.ai are both Cloudflare-protected — cf_clearance ties to TLS fingerprint; httpx gets rejected even with valid cookies, both providers now use curl_cffi"
metadata: 
  node_type: memory
  type: project
  originSessionId: c903d647-174d-46f2-8c61-8cf39dc278f1
  modified: 2026-07-19T01:49:37.463Z
---

`ai-usage`'s web-login-based usage providers (`CodexWebUsageProvider`, then `ClaudeWebUsageProvider`) kept failing even with genuinely valid, freshly-captured session cookies (confirmed via live pywebview login testing — captured cookies included the real NextAuth session tokens for Codex and `sessionKey`/`sessionKeyLC` for Claude). Root cause: **both** `chatgpt.com` and `claude.ai` sit behind Cloudflare, and `cf_clearance` is bound to the specific TLS/HTTP client fingerprint that solved the bot challenge (WebKitGTK's, since it was captured from a real pywebview login window). Replaying it from `httpx` — a different TLS stack — gets rejected regardless of cookie validity.

Codex's failure showed up as a direct 403 on `/api/auth/session`. Claude's showed up differently — as a silently-empty `/api/organizations` response, manifesting as "requires an 'org_id' option" rather than an exception, because that lookup is best-effort and swallows its own failure. Same underlying cause, different visible symptom — worth remembering if a THIRD provider shows yet another shape of "works with real cookies in a browser, fails via httpx."

**Fix applied to both:** switched every `httpx.AsyncClient` call site in `providers/claude.py` and `providers/codex.py` to `curl_cffi.requests.AsyncSession(..., impersonate="chrome")`, which presents a real Chrome TLS fingerprint. `curl-cffi` is a core dependency (not the `browser` extra) since these run on every headless scheduled crawl, no GUI involved.

**How to apply:** If any provider using cookie-based web scraping shows unexplained failures despite valid cookies, check whether that site is also Cloudflare-protected (look for `cf_clearance`/`__cf_bm`/`_cfuvid` in the captured cookie names, visible via the `print()` diagnostic in `webview_login.py`) — if so, the same `curl_cffi` swap is the fix, not more cookie-extraction debugging. See [[feedback_verify_thirdparty_return_shapes]] and [[feedback_native_gui_needs_real_run]] for related debugging lessons from this same investigation (source-reading + live testing found this, not guessing).
