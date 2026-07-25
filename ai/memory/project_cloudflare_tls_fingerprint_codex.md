---
name: project-cloudflare-tls-fingerprint-codex
description: "chatgpt.com AND claude.ai are both Cloudflare-protected — cf_clearance ties to TLS fingerprint; httpx gets rejected even with valid cookies, both providers now use curl_cffi"
metadata: 
  node_type: memory
  type: project
  originSessionId: c903d647-174d-46f2-8c61-8cf39dc278f1
  modified: 2026-07-19T01:49:37.463Z
---
`ai-usage` web-login providers (`CodexWebUsageProvider`, then `ClaudeWebUsageProvider`) kept fail despite genuinely valid, freshly-captured session cookies (confirmed via live pywebview login test — captured cookies had real NextAuth session tokens for Codex, `sessionKey`/`sessionKeyLC` for Claude). Root cause: **both** `chatgpt.com` and `claude.ai` sit behind Cloudflare, `cf_clearance` bound to specific TLS/HTTP client fingerprint that solved bot challenge (WebKitGTK's, captured from real pywebview login window). Replay via `httpx` — different TLS stack — rejected regardless cookie validity.

Codex failure: direct 403 on `/api/auth/session`. Claude failure different shape — silently-empty `/api/organizations` response, shows as "requires an 'org_id' option" not exception, since that lookup best-effort and swallows own failure. Same root cause, different symptom — remember if THIRD provider shows yet another "works with real cookies in browser, fails via httpx" shape.

**Fix applied both:** swapped every `httpx.AsyncClient` call site in `providers/claude.py` and `providers/codex.py` to `curl_cffi.requests.AsyncSession(..., impersonate="chrome")` — presents real Chrome TLS fingerprint. `curl-cffi` core dependency (not `browser` extra) since these run every headless scheduled crawl, no GUI involved.

**How to apply:** provider using cookie-based web scraping shows unexplained failure despite valid cookies → check if site also Cloudflare-protected (look for `cf_clearance`/`__cf_bm`/`_cfuvid` in captured cookie names, visible via `print()` diagnostic in `webview_login.py`) — if so, same `curl_cffi` swap is fix, not more cookie-extraction debugging. See [[feedback_verify_thirdparty_return_shapes]] and [[feedback_native_gui_needs_real_run]] for related debugging lessons same investigation (source-reading + live testing found this, not guessing).
