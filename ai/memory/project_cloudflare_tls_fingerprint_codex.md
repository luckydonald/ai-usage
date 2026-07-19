---
name: project-cloudflare-tls-fingerprint-codex
description: "chatgpt.com's Cloudflare protection ties cf_clearance to TLS fingerprint — httpx gets 403'd even with valid cookies; codex now uses curl_cffi"
metadata: 
  node_type: memory
  type: project
  originSessionId: c903d647-174d-46f2-8c61-8cf39dc278f1
  modified: 2026-07-19T01:43:39.232Z
---

`ai-usage`'s `CodexWebUsageProvider` (web-login based Codex usage scraping) kept 403ing even with genuinely valid, freshly-captured session cookies (confirmed via live pywebview login testing — the captured cookie set included the real NextAuth session tokens). Root cause: `chatgpt.com` sits behind Cloudflare, and its `cf_clearance` cookie is bound to the specific TLS/HTTP client fingerprint that solved the bot challenge (WebKitGTK's fingerprint, since the cookie was captured from a real pywebview login window). Replaying that cookie from `httpx` — a different TLS stack — gets rejected by Cloudflare regardless of cookie validity.

**Why this matters:** Fixed by switching `CodexWebUsageProvider.fetch()` from `httpx.AsyncClient` to `curl_cffi.requests.AsyncSession(..., impersonate="chrome")`, which presents a real Chrome TLS fingerprint. `curl-cffi` is now a core dependency (not the `browser` extra) since this runs on every headless scheduled crawl, no GUI involved.

**How to apply:** If `ClaudeWebUsageProvider` (or any other provider using cookie-based web scraping) starts showing similar unexplained 403s despite valid cookies, check whether that site is also Cloudflare-protected (look for `cf_clearance`/`__cf_bm`/`_cfuvid` in the captured cookie names) — if so, the same `curl_cffi` swap is the fix, not more cookie-extraction debugging. See [[feedback_verify_thirdparty_return_shapes]] and [[feedback_native_gui_needs_real_run]] for related debugging lessons from this same investigation (source-reading + live testing found this, not guessing).
