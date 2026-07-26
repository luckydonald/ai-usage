---
name: project_ai_usage_new_providers_batch
description: "8 new ai-usage providers added (Z.ai, MiniMax, Cline, OpenRouter, Cursor, Ollama Cloud, SuperGrok, Kimi), plus new shared _shared/ auth helpers"
metadata: 
  node_type: memory
  type: project
  originSessionId: ae3f5d59-bf5b-4a03-9fa5-5f15e5d1e6b3
  modified: 2026-07-26T06:28:33.440Z
---

Added Z.ai, MiniMax, Cline, OpenRouter (static API key), Cursor, Ollama Cloud (browser cookie-jar), SuperGrok (OAuth PKCE + local loopback), Kimi (OAuth device-flow RFC 8628) to `src/ai_usage/providers/`, following the existing `Provider`/`LoginMethod`/`UsageMethod` composition (see [[project_ai_usage_provider_add_wizard]]). Field names/cookies/endpoints were cross-checked against two reference IntelliJ plugins' actual source (`~/git/moritzfl/llm-subscription-usage-intellij`, `~/git/DimazzzZ/tokenpulse-intellij-plugin`), not just their doc summaries.

New shared package `src/ai_usage/providers/_shared/`: `static_api_key.py` (`StaticApiKeyLogin`, reused by 4 of the 8), `oauth_pkce.py` (generic PKCE + local-loopback-listener helper, see [[feedback_http_server_keepalive_hang]]), `oauth_device_flow.py` (generic RFC 8628 device-flow helper). Neither OAuth pattern existed in ai-usage before this — all prior login was cookie-jar-via-webview or local-token-reuse.

**Why:** user wanted the two reference plugins' provider coverage ported into ai-usage; picked 8 of ~15 possible providers in one batch, explicitly signing off on two providers (Kimi, OpenRouter) shipping with `user_identity()` unconditionally raising `ProviderLoginError` since neither vendor's API exposes any account-identifying field anywhere in the endpoints these providers call.

**How to apply:** `provider add` for Kimi and OpenRouter will always fail at the verify step (`cli.py`'s `verify_provider_setup`/`user_identity()` call, `cli.py:295` and `:738`) — this is accepted, not a bug to silently patch around. If asked to "fix" Kimi/OpenRouter login failing, check this memory first — the fix (if wanted) is either accepting a non-identifying pseudo-login or changing `cli.py`'s identity-handling itself, both explicitly deferred as out of scope when this batch shipped.
