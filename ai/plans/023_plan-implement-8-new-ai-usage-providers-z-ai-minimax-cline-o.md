# Plan: Implement 8 new AI-usage providers (Z.ai, MiniMax, Cline, OpenRouter, Cursor, Ollama Cloud, SuperGrok, Kimi)

## Context

Two prior inventory plans (`ai/plans/018_...md`, `ai/plans/019_...md`) catalogued how two comparable IntelliJ plugins (`llm-subscription-usage-intellij`, `tokenpulse-intellij-plugin`) fetch AI-vendor usage/quota data. Exploration confirmed `ai-usage` currently only ships 3 of the ~15 providers those inventories cover (Claude, Codex, Copilot — all fully wired via the `Provider`/`LoginMethod`/`UsageMethod` composition in `src/ai_usage/providers/base.py`). User selected 8 providers to add in this round, split by auth complexity:

- **Simple (static API key, `credential_kind="bearer_token"`)**: Z.ai, MiniMax, Cline, OpenRouter
- **Cookie-jar (reuse existing `capture_cookies_via_webview` pattern)**: Cursor, Ollama Cloud
- **New OAuth patterns (require new shared helpers — none exist in ai-usage today)**: SuperGrok (PKCE + local loopback), Kimi (RFC 8628 device flow)

Architecture (`base.py`, `registry.py`) was read directly and confirmed to match both Plan agents' descriptions: `LoginMethod.authenticate(options) -> dict|None`, `UsageMethod.fetch(account, credential) -> ProviderFetchResult`, `FallbackUsageMethod` (tries each method, catches only `ProviderError`, credential kind taken from `methods[0]`), `Provider` (composition root, `matching_login_methods()` filters by `credential_kind == required_credential_kind`, `user_identity()` is abstract/raises `NotImplementedError` by default). `registry.built_in_registry()` is a flat tuple of provider instances — new providers just get imported and appended, no other CLI wiring needed (the `provider add` wizard in `cli.py` — `select_provider`, `resolve_login_method`, `run_provider_add_wizard`, `create_account` — is fully generic over any registered `Provider`).

User decisions locked in:
- If a vendor has no confirmed identity/email field, `user_identity()` should **raise `ProviderLoginError`** (matches existing `CopilotEntitlementsProvider`/`CodexStatusProvider` precedent) rather than fall back to a synthetic placeholder — implementers should still try any plausible profile field first, only raising when truly nothing identifies the account.
- HTML parsing dependency for Ollama: **beautifulsoup4** (not selectolax).
- Cross-checked against both reference repos' actual source (not just the inventory summaries) for exact field names/cookies/URLs — see per-provider sections below. Confirmed `user_identity()` raising any `ProviderError` is caught at both call sites in `cli.py` (lines 295-301 and 738-745) and turned into a hard `click.ClickException` — this **blocks `provider add` setup entirely**, with no `--secret-json`/`--secret-file` bypass (the same `verify_provider_setup`/probe-fetch path runs regardless of how the credential was obtained).
  - **Cline**: reference plugin's `/users/me` response has no email, but does have `data.id` (account id string) — use that as the identity value (satisfies "try any plausible field first"), not a raise.
  - **OpenRouter**: confirmed no identity field anywhere in the credits/activity responses — `user_identity()` will raise `ProviderLoginError`, same practical effect as Kimi (see below). User has not separately overridden this; flagged as a real limitation to mention when implementation is done.
  - **Kimi**: confirmed zero identity signal anywhere in Kimi's OAuth/usage flow (no id, no email, no JWT decode in the reference plugin). **User's explicit decision: keep the strict raise — ship Kimi's provider code as-is, accept that `provider add` will always fail at the verify step** until/unless `cli.py`'s identity-handling is changed later (out of scope for this plan).
  - **SuperGrok**: usage/billing/settings endpoints also carry no identity field, but the OAuth scope requests `openid profile email` — **user's explicit decision: attempt best-effort decode of the token-exchange response's `id_token` JWT (no signature verification, matching ai-usage's existing unverified-JWT-claim-read pattern used elsewhere) for an `email`/`sub` claim**; only raise `ProviderLoginError` if no `id_token` is returned or it has no usable claim.

## New shared infrastructure

### `src/ai_usage/providers/_shared/` (new package)

1. **`oauth_pkce.py`** — `run_pkce_login(*, authorization_endpoint, token_endpoint, client_id, redirect_uri, scopes, extra_authorize_params=None, callback_timeout=300.0) -> PkceExchange`. Generates PKCE verifier/challenge (`secrets.token_urlsafe` + SHA-256/base64url) and `state`, opens the system browser via `webbrowser.open`, runs a short-lived `http.server.HTTPServer` in a background thread bound to `redirect_uri`'s fixed host:port (e.g. xAI's `127.0.0.1:56121`) to catch the `?code=&state=` callback, bridges into the async caller via `asyncio.wait_for(asyncio.to_thread(queue.get), timeout=callback_timeout)`, exchanges the code via `httpx.AsyncClient` POST to `token_endpoint`. Raises `ProviderError` on timeout, state mismatch, non-2xx token response, or `OSError` from a busy port (clear "port already in use" message, since xAI's redirect port is fixed and not configurable).

2. **`oauth_device_flow.py`** — `run_device_flow_login(*, device_authorization_endpoint, token_endpoint, client_id, scope=None, display_prompt=<click.echo default>, poll_timeout=600.0) -> DeviceFlowTokens`. POSTs to the device-authorization endpoint, calls `display_prompt(user_code, verification_uri)` once (default impl does `click.echo` + `webbrowser.open`), polls the token endpoint on the server-given `interval` handling `authorization_pending` (keep polling), `slow_down` (+5s), `expired_token`/`access_denied` (raise `ProviderError`). `display_prompt` is injectable so `_shared` has no hard `click` dependency and so tests can pass a fake. Confirmed structurally compatible with `cli.py`'s existing await-based `login_method.authenticate()` call sites (plain `click.echo`, no rich/Console layer anywhere in the CLI) — no CLI restructuring required.

Both helpers are pure-`httpx`/`asyncio`/stdlib (no `curl_cffi`) since none of xAI's or Kimi's OAuth endpoints are described as Cloudflare-fronted. Add `tests/test_oauth_pkce.py` and `tests/test_oauth_device_flow.py` using `respx` for the token endpoints and injected fakes for the browser-opening/local-server side, so these are tty-independent and CI-safe.

## Simple API-key providers

### Shared login helper: `src/ai_usage/providers/_shared/static_api_key.py`

`StaticApiKeyLogin(LoginMethod)` — `credential_kind="bearer_token"`; constructor takes `display_name`, `prompt_label="API key"`, optional `validate: Callable[[str], Awaitable[None]] | None`. `authenticate()` does `click.prompt(prompt_label, hide_input=True)`, strips, raises `ProviderLoginError` if empty, runs `validate` if given, returns `{"token": key}`. Reused directly (no per-provider login file needed) by Z.ai, Cline, OpenRouter. MiniMax needs its own subclass (`minimax/login/local/api_key.py`) since the `region` config field must be known before/alongside the key.

### 1. Z.ai — `src/ai_usage/providers/zai/`
- `usage/web/private_api.py`: `ZaiUsage(UsageMethod)`, plain `httpx.AsyncClient(base_url="https://api.z.ai")`, `Authorization: Bearer <token>`. GET `/api/biz/subscription/list` (detect no-plan via `success=False` + message containing "coding plan"/"不存在" → raise `ProviderError`; 401/403 → invalid-key error). GET `/api/monitor/usage/quota/limit`, split `limits[]` by `type`: `TOKENS_LIMIT` sorted by `number * unit_to_ms(unit)` ascending → shortest = session, 2nd-shortest = weekly; `TIME_LIMIT` → web-search window. `unit` mapping `{1:"days",3:"hours",5:"minutes",6:"weeks"}`.
- `provider.py`: `ZaiProvider`, `configuration_fields=()`, `login_methods=(StaticApiKeyLogin(display_name="Z.ai API key"),)`.

### 2. MiniMax — `src/ai_usage/providers/minimax/`
- `configuration_fields=(ConfigurationField(key="region", label="Region", required=True, help="global or cn"),)` — plain string prompted via existing generic `create_account()` `click.prompt` path, no CLI changes.
- `usage/web/private_api.py`: region-keyed ordered URL tuples (global: 3 URLs, cn: 2 URLs per the inventory), try in order, stop on first parseable success, 401/403 short-circuits entirely, `base_resp.status_code != 0` tries next URL. Field-priority helper for used/remaining (`current_interval_usage_count` → `_remaining_count` → `_remains_count`), timestamp heuristic (`value < 10_000_000_000` ⇒ seconds). Use whichever plan-name field is present verbatim — no static lookup table (per Plan agent's own recommendation, avoids staleness).

### 3. Cline — `src/ai_usage/providers/cline/`
- `usage/web/private_api.py`: base `https://api.cline.bot`, header `Authorization: Bearer <token>` on every call. Response envelope everywhere: `{"success": bool, "data": {...}}` — only treat as valid if `success == true`.
  - `GET /api/v1/users/me` → `data.id` (string) — used both to build subsequent URLs and as the identity value. No email field exists. 401/403 → invalid key; 429 → rate limited; ≥500 → transient/network error (not auth).
  - `GET /api/v1/users/{id}/balance` → `data.balance` (number, **micro-dollars**: divide by 1_000_000, round to 2dp for USD).
  - `GET /api/v1/users/{id}/usages` → `data.items: [{creditsUsed, totalTokens}]` — sum `creditsUsed` (same micro-dollar conversion) and `totalTokens` across items.
  - `GET /api/v1/users/me/plan/usage-limits` → `data.limits: [{type, percentUsed, resetsAt}]`, recognized `type` values (literal): `"five_hour"`, `"weekly"`, `"monthly"` (others dropped). `percentUsed` clamped 0-100.
  - Best-effort semantics: only the `/users/me` call is auth-gating/fatal; balance/usages/plan-limits failures should degrade to zero/empty rather than aborting the whole fetch (matches reference plugin behavior) — use `asyncio.gather(..., return_exceptions=True)` for the latter three, `ProviderError` only from `/users/me`.
  - `user_identity()`: return `data.id` from `/users/me` (a real, stable field — not a raise).

### 4. OpenRouter — `src/ai_usage/providers/openrouter/`
- `usage/web/private_api.py`: base `https://openrouter.ai`, header `Authorization: Bearer <provisioning_key>` (must be a Provisioning Key — regular API keys don't expose `/credits`, per reference plugin's explicit comment).
  - `GET /api/v1/credits` → `{"data": {"total_credits": number, "total_usage": number|null}}`. `used = total_usage or 0`; `remaining = total_credits - used`.
  - `GET /api/v1/activity` (best-effort, don't fail the whole fetch if it errs) → `{"data": [{"prompt_tokens": int, "completion_tokens": int}, ...]}`, sum both fields across entries for a token-count metric.
  - Error mapping: 401 → auth error; 429 → rate limited; any other non-2xx (**including 403**) → generic/unknown error (not auth-specific, per reference plugin).
  - `user_identity()`: no identity field exists anywhere in these two endpoints — raise `ProviderLoginError` (same practical limitation as Kimi; flag to user post-implementation).

Registry diff: import 4 new providers in `registry.py`, append to `built_in_registry()`'s tuple.

## Cookie-jar providers

### 5. Cursor — `src/ai_usage/providers/cursor/`
- `login/web/cookie_capture.py`: `CookieCaptureLogin` (`credential_kind="cookie_jar"`), target `https://cursor.com/login`, capture cookie `WorkosCursorSessionToken` — **confirmed this is the literal browser cookie name** (not just an internal storage key), format `userId::accessToken`, URL-encoded as `userId%3A%3AaccessToken`.
- Helper `extract_cursor_bearer_token(cookies)`: URL-decode the `WorkosCursorSessionToken` value, split on `"::"`, take the JWT half (fallback: whole value if it starts with `"eyJ"`, no separator found). Also `extract_user_id` (substring before `"::"`) as a fallback if `/api/auth/me`'s `sub` isn't available.
- `usage_method = FallbackUsageMethod((PrivateApiUsage(), GrpcJsonUsage()))` — both legs `credential_kind="cookie_jar"`.
  - `usage/web/private_api.py` (preferred, cookie path): `curl_cffi.requests.AsyncSession(impersonate="chrome", base_url="https://cursor.com")`, header `Cookie: WorkosCursorSessionToken=<token>`, `Accept: application/json`.
    - `GET /api/usage-summary` → `UsageSummaryResponse{billingCycleStart, billingCycleEnd, membershipType, limitType, isUnlimited, autoModelSelectedDisplayMessage, namedModelSelectedDisplayMessage, individualUsage:{plan:{enabled,used,limit,remaining,breakdown:{included,bonus,total},autoPercentUsed,apiPercentUsed,totalPercentUsed}, onDemand:{enabled,used,limit,remaining}, overall:{enabled,used,limit,remaining}}, teamUsage:{onDemand,pooled}}`.
    - `GET /api/auth/me` (best-effort) → `{email, name, sub, email_verified}` — `email` is the identity value; `sub` used as userId fallback.
    - `GET /api/usage?user=<urlencoded userId>` → `RequestUsageResponse{"gpt-4":{numRequests,numRequestsTotal,numTokens,maxRequestUsage,maxTokenUsage}, startOfMonth}`.
    - Monetary fields are in **cents** throughout — divide by 100 for USD. Raise `ProviderError` (not swallow) on the primary `/api/usage-summary` call failing, so `FallbackUsageMethod` proceeds to the gRPC leg. 401/403 → invalid/expired session message.
  - `usage/web/grpc_json.py` (fallback, bearer-token path — used when only an access token is available, no cookie, or the cookie path failed): `curl_cffi.requests.AsyncSession(base_url="https://api2.cursor.sh")`, `Authorization: Bearer <jwt>`, `Content-Type: application/json` (plus `Cookie` header too if present).
    - `POST /aiserver.v1.DashboardService/GetCurrentPeriodUsage` body literal `"{}"` → `CurrentPeriodUsageResponse{billingCycleStart, billingCycleEnd, planUsage:{totalSpend,includedSpend,bonusSpend,limit,autoPercentUsed,apiPercentUsed,totalPercentUsed}, spendLimitUsage:{totalSpend,pooledLimit,pooledUsed,pooledRemaining,individualUsed,limitType}, displayThreshold, displayMessage, autoModelSelectedDisplayMessage, namedModelSelectedDisplayMessage}` — cents throughout.
    - `POST /aiserver.v1.DashboardService/GetPlanInfo` body `"{}"` (best-effort) → `{planInfo:{planName, includedAmountCents, price, billingCycleEnd}}`.
    - `GET /auth/full_stripe_profile` (best-effort) → `{membershipType, isTeamMember}`.
    - 401/403 → "Cursor session is invalid or expired" style message.
  - `user_identity()`: `/api/auth/me`'s `email` field when the cookie path succeeded; if only the gRPC/bearer path ran (no `/api/auth/me` call made), fall back to the JWT's own claims (decode without signature verification) for an `email`/`sub` claim, else `ProviderLoginError`.

### 6. Ollama Cloud — `src/ai_usage/providers/ollama/`
- `login/web/cookie_capture.py`: same pattern, target `https://ollama.com`, captures cookies `__Secure-session` (required) and `cf_clearance` (optional, best-effort) — **confirmed literal cookie names** used verbatim in the `Cookie` header (`"__Secure-session=<value>"`, joined with `"; cf_clearance=<value>"` if present).
- `usage/web/settings_scrape.py`: `GET https://ollama.com/settings`, headers `Cookie: <built above>`, `Accept: text/html`, spoofed `User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36` (plain `httpx.AsyncClient` first; escalate to `curl_cffi` if live testing shows 403s). Parse HTML with **beautifulsoup4**:
  - Plan: find `<h2>` containing text "Cloud Usage"; within its section, find `span.capitalize`, take `.text.strip().lower()`, validate against `{"free", "pro", "max"}` (fallback: scan all `span[class~=capitalize]` in the doc if not found within the h2 section).
  - Usage windows: find `<span class="text-sm">` whose text is exactly `"Session usage"` or `"Weekly usage"` (literal label match, not substring); from that span walk **up** parents until an ancestor contains both a `div[style*="width:"]` and an element with a `data-time` attribute — that's the "usage window block".
  - Percent: within the block, first `div[style*="width:"]`, regex `width:\s*([0-9.]+)%` against the `style` attribute.
  - Reset time: within the block, first element with `data-time` attribute, parse as ISO instant.
  - **Fail loudly** (`ProviderError`, message like "Could not parse Ollama quota from HTML — page layout may have changed") if both session and weekly windows come back null, rather than silently returning 0%/empty — this is the only HTML-scraping provider in the codebase and is inherently coupled to ollama.com's frontend markup. 401/403 → "Ollama session cookie is invalid or expired" message.
  - `user_identity()`: the settings page is not confirmed to expose an email/username element in the scraped inventory — attempt a best-effort scrape (e.g. an account/email element elsewhere on `/settings`) during implementation; raise `ProviderLoginError` if genuinely absent.
- Add `beautifulsoup4` to `pyproject.toml` dependencies.

Registry diff: import `CursorUsageProvider`, `OllamaCloudUsageProvider`, append to tuple.

## New-OAuth providers

### 7. SuperGrok (xAI) — `src/ai_usage/providers/supergrok/`
- `login/web/pkce_login.py`: thin `PkceLogin(LoginMethod)` wrapper around `_shared/oauth_pkce.run_pkce_login`, hardcoding xAI's confirmed constants: `authorization_endpoint=https://auth.x.ai/oauth2/authorize`, `client_id=b1a00492-073a-47ea-816f-4c329264a828`, `token_endpoint=https://auth.x.ai/oauth2/token`, `redirect_uri=http://127.0.0.1:56121/callback`, `scopes="openid profile email offline_access grok-cli:access api:access"`, extra authorize params `{"plan": "generic", "referrer": "openai-usage-quota-plugin"}`, `include_nonce=True` (`oauth_pkce.run_pkce_login` needs an `extra_authorize_params` passthrough — already in its designed signature — plus a `nonce` param to add since xAI's flow includes one; extend the shared helper's signature with an optional `include_nonce: bool = False` that appends a random `nonce` to the authorize URL when set).
  - **Identity**: after token exchange, check the token response for an `id_token` field; if present, decode its JWT claims (no signature verification — `base64.urlsafe_b64decode` the payload segment, same pattern as other unverified-JWT-claim reads in the codebase) and look for `email` then `sub`. Return that as the credential's stashed identity hint (e.g. `credential["identity_hint"]`) so `user_identity()` doesn't need a second network call.
- `usage/web/billing_api.py`: `httpx.AsyncClient` (not Cloudflare-fronted per spec), base `https://cli-chat-proxy.grok.com/v1/`.
  - `GET billing?format=credits` (required), headers `Authorization: Bearer <token>`, `X-XAI-Token-Auth: xai-grok-cli`, `Accept: application/json`, `User-Agent: LLM Subscription Usage`. Retry once if response is HTTP 400 with JSON body `{"code": "The operation was cancelled", "error": "Timeout expired"}` (case-insensitive check).
  - `GET settings` (best-effort, same headers) → top-level `subscription_tier_display` string used as plan display name.
  - Parse `billing?format=credits` via a dynamic dict walk (not a strict pydantic model, root shape is genuinely two possible forms): root is `config`, or `billing.config` if nested. Within `config`: `used` and `monthlyLimit` (each may be a raw number OR `{"val": N}` — write a small `unit_value(obj, key)` helper handling both), `creditUsagePercent` (float, prefer over computing manually), `productUsage` (list of `{usagePercent}`, take max as fallback), `currentPeriod: {start, end, type}` (fallback to top-level `billingPeriodStart`/`billingPeriodEnd`), `isUnifiedBillingUser` (bool), `onDemandCap`.
- `provider.py`: `SuperGrokBillingProvider`, `login_methods=(PkceLogin(),)`. `user_identity()`: return the `identity_hint` stashed by `PkceLogin.authenticate()` if present; else raise `ProviderLoginError` (per user decision — best-effort JWT decode first, only raise if no `id_token` or no usable claim).

### 8. Kimi (Moonshot) — `src/ai_usage/providers/kimi/`
- `login/web/device_flow_login.py`: thin `DeviceFlowLogin(LoginMethod)` wrapper around `_shared/oauth_device_flow.run_device_flow_login`, hardcoding confirmed constants: `device_authorization_endpoint=https://auth.kimi.com/api/oauth/device_authorization`, `client_id=17e5f671-d194-4dfb-9706-5516cb48c098`, `token_endpoint=https://auth.kimi.com/api/oauth/token`. Every OAuth POST (device-authorization and token/poll) must send Kimi's device-fingerprint headers: `X-Msh-Platform: kimi_cli`, `X-Msh-Version: 1.40.0`, `X-Msh-Device-Name` (sanitized hostname), `X-Msh-Device-Model` (e.g. `"macOS 14.5 arm64"`), `X-Msh-Os-Version`, `X-Msh-Device-Id` (random UUID, dashes stripped, persisted locally so repeated logins reuse the same device id — store alongside other local state, not in the credential itself). This means `_shared/oauth_device_flow.run_device_flow_login` needs an `extra_headers: dict[str,str] | None` passthrough param used on every request it makes, since these headers are vendor-specific, not part of RFC 8628 itself.
- `usage/web/usages_api.py`: `GET https://api.kimi.com/coding/v1/usages`, headers `Authorization: Bearer <token>`, `Accept: application/json` (no `X-Msh-*` headers on this call — those are OAuth-only). Response: `{usage, limits: [{window: {duration, timeUnit}, detail: {limit, remaining, resetTime}}], user: {membership: {level}}}`. `limit`/`remaining` are **strings** — parse via float-safe conversion (treat unparsable as 0). Session window = entry where `window.duration == 300 and window.timeUnit == "TIME_UNIT_MINUTE"`, fallback `limits[0]`. `used = max(0, limit - remaining)`. Build one `Metric` per relevant window; `reset_at` from `detail.resetTime` (ISO, guarded parse). Membership level values `LEVEL_INTERMEDIATE`/`LEVEL_ADVANCED`/`LEVEL_PREMIUM` map to display strings `"Kimi Code Intermediate/Advanced/Premium"` (title-case the `LEVEL_` suffix as a fallback for unknown levels).
- `user_identity()`: **confirmed zero identity signal exists anywhere in Kimi's OAuth/usage flow** (no id, no email, no JWT decode in the reference plugin either) — raise `ProviderLoginError` unconditionally. **User's explicit decision: ship this as-is** — `provider add` for Kimi will always fail at the verify step until `cli.py`'s identity-handling changes (out of scope here); document this clearly in the provider's docstring/README entry so it isn't mistaken for a bug later.

Registry diff: import `SuperGrokBillingProvider`, `KimiUsageProvider`, append to tuple.

## Files to modify
- `src/ai_usage/providers/registry.py` — 8 new imports + 8 new tuple entries in `built_in_registry()`.
- `pyproject.toml` — add `beautifulsoup4` dependency.
- `tests/test_providers.py` — parser/logic unit tests per provider (Z.ai window-sort/no-plan detection, MiniMax fallback-chain + field-priority, Cline partial-success combine, OpenRouter dual-shape normalizer, Cursor token-extraction + cents conversion, Ollama HTML-extraction functions with inline fixtures, xAI dual-root normalizer, Kimi string-field parsing), using existing `respx` (httpx) / `FakeCurlResponse` (curl_cffi) patterns already present in that file.
- New `tests/test_oauth_pkce.py`, `tests/test_oauth_device_flow.py`.

## Known risks / open items (field names/cookies/URLs above are now confirmed against actual reference-plugin source, not guessed — remaining risk is vendor-API drift since these three APIs are unofficial/reverse-engineered)
- Cursor's, Kimi's, SuperGrok's endpoints are all unofficial/reverse-engineered by the reference plugins (no public docs) — they can change without notice; ai-usage's error handling should surface such breakage clearly (labeled `ProviderError`, not a silent empty result) rather than assuming these shapes are permanently stable.
- **Kimi and OpenRouter will always fail `provider add`'s verify step** (`user_identity()` raises `ProviderLoginError` unconditionally for Kimi; unconditionally for OpenRouter since neither exposes any identity field) — this is accepted as a known, documented limitation per user decision, not a bug to silently work around.
- SuperGrok's identity resolution depends on whether xAI's token endpoint actually returns an `id_token` in practice when scope includes `openid` — needs live confirmation; if absent, SuperGrok has the same permanent-verify-failure limitation as Kimi/OpenRouter.
- Ollama's HTML structure is a live scrape target coupled to ollama.com's current frontend markup/class names — most fragile of the 8 by nature, independent of implementation correctness.

## Verification
- Run existing test suite (`pytest`) plus new provider-specific tests — validates parsing/fallback logic without network access.
- `ai-usage provider add` for each new provider against the real vendor, for a human with real credentials and a real browser — this repo's environment has no tty/display (per project memory: "Native GUI needs a real run", "No tty environment"), so the cookie-capture (Cursor/Ollama) and browser-based OAuth (SuperGrok/Kimi) login flows cannot be exercised end-to-end here.
- Note: `--secret-json`/`--secret-file` bypasses `LoginMethod.authenticate()` but **not** `verify_provider_setup`'s probe-fetch + `user_identity()` call — so even non-interactive credential injection can't sidestep the Kimi/OpenRouter identity-blocker above. Z.ai/MiniMax/Cline (all with real identity fields) can be smoke-tested end-to-end here if the user supplies a real key via `--secret-json`/`--secret-file`.
- After implementation, ask the user to run each new provider's login flow locally and confirm a real `ai-usage status`/`ai-usage usage` fetch succeeds, since none of the webview/OAuth machinery can be verified from this session.

## Todos

- [x] Shared: _shared/static_api_key.py
- [x] Shared: _shared/oauth_pkce.py
- [x] Shared: _shared/oauth_device_flow.py
- [x] Provider: Z.ai
- [x] Provider: MiniMax
- [x] Provider: Cline
- [x] Provider: OpenRouter
- [x] Provider: Cursor
- [x] Provider: Ollama Cloud
- [x] Provider: SuperGrok
- [x] Provider: Kimi
- [x] Wire registry.py
- [x] Add beautifulsoup4 to pyproject.toml
- [x] Tests for all new providers + shared helpers
- [x] Run full test suite
