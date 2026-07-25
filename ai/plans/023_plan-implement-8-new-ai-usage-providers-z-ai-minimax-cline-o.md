# Plan: Implement 8 new AI-usage providers (Z.ai, MiniMax, Cline, OpenRouter, Cursor, Ollama Cloud, SuperGrok, Kimi)

## Context

Two prior inventory plans (`ai/plans/018_...md`, `ai/plans/019_...md`) catalogued how two comparable IntelliJ plugins (`llm-subscription-usage-intellij`, `tokenpulse-intellij-plugin`) fetch AI-vendor usage/quota data. Exploration confirmed `ai-usage` currently only ships 3 of the ~15 providers those inventories cover (Claude, Codex, Copilot — all fully wired via the `Provider`/`LoginMethod`/`UsageMethod` composition in `src/ai_usage/providers/base.py`). User selected 8 providers to add in this round, split by auth complexity:

- **Simple (static API key, `credential_kind="bearer_token"`)**: Z.ai, MiniMax, Cline, OpenRouter
- **Cookie-jar (reuse existing `capture_cookies_via_webview` pattern)**: Cursor, Ollama Cloud
- **New OAuth patterns (require new shared helpers — none exist in ai-usage today)**: SuperGrok (PKCE + local loopback), Kimi (RFC 8628 device flow)

Architecture (`base.py`, `registry.py`) was read directly and confirmed to match both Plan agents' descriptions: `LoginMethod.authenticate(options) -> dict|None`, `UsageMethod.fetch(account, credential) -> ProviderFetchResult`, `FallbackUsageMethod` (tries each method, catches only `ProviderError`, credential kind taken from `methods[0]`), `Provider` (composition root, `matching_login_methods()` filters by `credential_kind == required_credential_kind`, `user_identity()` is abstract/raises `NotImplementedError` by default). `registry.built_in_registry()` is a flat tuple of provider instances — new providers just get imported and appended, no other CLI wiring needed (the `provider add` wizard in `cli.py` — `select_provider`, `resolve_login_method`, `run_provider_add_wizard`, `create_account` — is fully generic over any registered `Provider`).

User decisions locked in:
- If a vendor has no confirmed identity/email field, `user_identity()` should **raise `ProviderLoginError`** (matches existing `CopilotEntitlementsProvider`/`CodexStatusProvider` precedent) rather than fall back to a synthetic placeholder — implementers should still try any plausible profile field first (e.g. Cline's `/users/me`, Kimi's `user.membership`), only raising when truly nothing identifies the account.
- HTML parsing dependency for Ollama: **beautifulsoup4** (not selectolax).

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
- `usage/web/private_api.py`: base `https://api.cline.bot/api/v1/`, fetch `/users/me`, `/users/balance`, `/users/usages`, `/users/plan/usage-limits` via `asyncio.gather(..., return_exceptions=True)` — best-effort combine, only raise `ProviderError` if **all four** fail. Build `Metric`s from whatever succeeds; identity from `/users/me`.

### 4. OpenRouter — `src/ai_usage/providers/openrouter/`
- `usage/web/private_api.py`: base `https://openrouter.ai/`, `Authorization: Bearer <provisioning_key>`. **Before implementing**, confirm live endpoint/field shape (`/api/v1/credits` → `data.total_credits`/`data.total_usage`, vs `/api/v1/auth/key` → `data.limit`/`data.usage`/`data.limit_remaining` — these are genuinely different shapes) against OpenRouter's current public API docs; write one normalizer function that accepts either envelope defensively.

Registry diff: import 4 new providers in `registry.py`, append to `built_in_registry()`'s tuple.

## Cookie-jar providers

### 5. Cursor — `src/ai_usage/providers/cursor/`
- `login/web/cookie_capture.py`: thin `CookieCaptureLogin` copy (same shape as Claude's/Codex's — `credential_kind="cookie_jar"`), target `https://cursor.com/login` (verify against live site during implementation).
- Helper `extract_cursor_bearer_token(cookies)`: URL-decode `WorkosCursorSessionToken` cookie (confirm exact cookie name live — reverse-engineered, not officially documented), split on `::`, take the JWT half (or whole value if it starts with `eyJ`).
- `usage_method = FallbackUsageMethod((PrivateApiUsage(), GrpcJsonUsage()))` — both legs use `credential_kind="cookie_jar"` (consistent, satisfies `FallbackUsageMethod.required_credential_kind = methods[0].required_credential_kind`).
  - `usage/web/private_api.py`: `curl_cffi.requests.AsyncSession(impersonate="chrome")` (cursor.com likely Cloudflare-fronted like claude.ai), GET `/api/usage-summary`, best-effort `/api/auth/me`, GET `/api/usage?user=<id>`. Money fields in cents → divide by 100. Must raise `ProviderError` (not swallow) on failure so the fallback triggers.
  - `usage/web/grpc_json.py`: `curl_cffi.requests.AsyncSession(base_url="https://api2.cursor.sh")`, `Authorization: Bearer <jwt>`, POST `/aiserver.v1.DashboardService/GetCurrentPeriodUsage` body `"{}"`, best-effort `GetPlanInfo` + `/auth/full_stripe_profile`.

### 6. Ollama Cloud — `src/ai_usage/providers/ollama/`
- `login/web/cookie_capture.py`: same pattern, target `https://ollama.com`, captures `__Secure-session` (required) + `cf_clearance` (optional, best-effort).
- `usage/web/settings_scrape.py`: GET `https://ollama.com/settings` (plain `httpx.AsyncClient` first; escalate to `curl_cffi` if live testing shows 403s), parse HTML with **beautifulsoup4**. Extract plan from `<h2>` "Cloud Usage" section's nested `class="capitalize"` span; usage % from progress-bar `style="width:NN%"` found by walking up from a `<span class="text-sm">` labeled "Session usage"/"Weekly usage" (bounded upward traversal, regex `width:\s*([0-9.]+)%`); reset time from `[data-time]` attribute. **Fail loudly** (`ProviderError`) if expected structure isn't found, rather than silently returning 0%/empty — this is the only HTML-scraping provider in the codebase and is inherently coupled to ollama.com's frontend markup.
- Add `beautifulsoup4` to `pyproject.toml` dependencies.

Registry diff: import `CursorUsageProvider`, `OllamaCloudUsageProvider`, append to tuple.

## New-OAuth providers

### 7. SuperGrok (xAI) — `src/ai_usage/providers/supergrok/`
- `login/web/pkce_login.py`: thin `PkceLogin(LoginMethod)` wrapper around `_shared/oauth_pkce.run_pkce_login`, hardcoding xAI's `authorization_endpoint=https://auth.x.ai/oauth2/authorize`, `client_id=b1a00492-073a-47ea-816f-4c329264a828`, `redirect_uri=http://127.0.0.1:56121/callback`, scopes `openid profile email offline_access grok-cli:access api:access`, `token_endpoint=https://auth.x.ai/oauth2/token`.
- `usage/web/billing_api.py`: `httpx.AsyncClient`, GET `https://cli-chat-proxy.grok.com/v1/billing?format=credits` (`Authorization: Bearer`, `X-XAI-Token-Auth: xai-grok-cli`), best-effort GET `.../settings`. Response root is ambiguous (`{config:{...}}` or `{billing:{config:{...}}}`) — write a small normalizer (`payload.get("billing", payload).get("config", {})`) rather than a strict pydantic model; confirm exact leaf field names live before finalizing the `Metric` builder.
- `provider.py`: `SuperGrokBillingProvider`, `login_methods=(PkceLogin(),)`. `user_identity()`: try any account/profile field from the billing/settings responses; raise `ProviderLoginError` if none found (per user decision).

### 8. Kimi (Moonshot) — `src/ai_usage/providers/kimi/`
- `login/web/device_flow_login.py`: thin `DeviceFlowLogin(LoginMethod)` wrapper around `_shared/oauth_device_flow.run_device_flow_login`, hardcoding `device_authorization_endpoint=https://auth.kimi.com/api/oauth/device_authorization`, `client_id=17e5f671-d194-4dfb-9706-5516cb48c098`, `token_endpoint=https://auth.kimi.com/api/oauth/token`.
- `usage/web/usages_api.py`: GET `https://api.kimi.com/coding/v1/usages` (`Authorization: Bearer`). `limits[]` items have **string** `limit`/`remaining` fields — parse as float. Session window = entry where `window.duration==300 && window.timeUnit=="TIME_UNIT_MINUTE"`, fallback `limits[0]`. `used = max(0, limit - remaining)`. Build one `Metric` per relevant window; `reset_at` from `detail.resetTime` (ISO, guarded parse). Identity from `user.membership.level` if present, else `ProviderLoginError`.

Registry diff: import `SuperGrokBillingProvider`, `KimiUsageProvider`, append to tuple.

## Files to modify
- `src/ai_usage/providers/registry.py` — 8 new imports + 8 new tuple entries in `built_in_registry()`.
- `pyproject.toml` — add `beautifulsoup4` dependency.
- `tests/test_providers.py` — parser/logic unit tests per provider (Z.ai window-sort/no-plan detection, MiniMax fallback-chain + field-priority, Cline partial-success combine, OpenRouter dual-shape normalizer, Cursor token-extraction + cents conversion, Ollama HTML-extraction functions with inline fixtures, xAI dual-root normalizer, Kimi string-field parsing), using existing `respx` (httpx) / `FakeCurlResponse` (curl_cffi) patterns already present in that file.
- New `tests/test_oauth_pkce.py`, `tests/test_oauth_device_flow.py`.

## Known risks / open items to resolve during implementation (not blocking, but must be checked against live vendor responses before considering each provider done)
- OpenRouter endpoint/field shape (`/credits` vs `/auth/key`).
- Cursor's exact cookie name and `/api/usage-summary`/`GetCurrentPeriodUsage` field names (reverse-engineered API, no official docs).
- xAI billing/settings and Kimi `/usages` exact identity-bearing fields (may end up raising `ProviderLoginError` per user's chosen policy if truly absent).
- Ollama's HTML structure is a live scrape target — verify class names against the real rendered page.

## Verification
- Run existing test suite (`pytest`) plus new provider-specific tests — validates parsing/fallback logic without network access.
- `ai-usage provider add` for each new provider against the real vendor, for a human with real credentials and a real browser — this repo's environment has no tty/display (per project memory: "Native GUI needs a real run", "No tty environment"), so the cookie-capture (Cursor/Ollama) and browser-based OAuth (SuperGrok/Kimi) login flows cannot be exercised end-to-end here. Static-API-key providers (Z.ai/MiniMax/Cline/OpenRouter) can at least be smoke-tested end-to-end here if the user supplies a real key via `--secret-json`/`--secret-file` (bypasses interactive `authenticate()` entirely, per existing `cli.py:600-604` mechanism).
- After implementation, ask the user to run each new provider's login flow locally and confirm a real `ai-usage status`/`ai-usage usage` fetch succeeds, since none of the webview/OAuth machinery can be verified from this session.
