Have enough exact detail. Writing report.

## Ollama

**Credential source:** Two separate secrets, both pasted by user into `OllamaSettingsPanel`, stored in IntelliJ PasswordSafe:
- Session cookie — row label "Session cookie (__Secure-session):", helper text: "Extract from ollama.com → DevTools → Storage → Cookies. Paste `__Secure-session` (required) and `cf_clearance` (optional)." Required for quota fetching. Stored via `OllamaSessionCookieStore` under PasswordSafe service `"Ollama Session Cookie"` / username `"ollama-session"`.
- `cf_clearance` cookie — optional, tooltip "cf_clearance cookie from ollama.com (optional, helps bypass Cloudflare)". Stored under service `"Ollama CF Clearance"` / username `"ollama-cf"`.
- API key — separate field, tooltip "Ollama API key from ollama.com/settings/keys (used for MCP web search and proxy)". Explicitly NOT used for quota fetch, only for web-search/proxy. Stored via `OllamaApiKeyStore`, service `"Ollama API Key"` / username `"ollama-api-key"`.

No OAuth flow — pure manual cookie-paste. `OllamaApiKeyStore`/`OllamaSessionCookieStore` are `@Service(APP)` singletons wrapping `PasswordSafe.instance.get/set`, async-loaded off EDT with an atomic generation counter to avoid stale-load races.

**No token refresh logic** — cookie is static until user re-pastes it.

**API calls:**
1. `GET https://ollama.com/settings` — quota fetch. NOT a JSON API, it's HTML scraped with Jsoup. Headers: `Cookie: __Secure-session=<sessionCookie>[; cf_clearance=<cfClearance>]`, `Accept: text/html`, `User-Agent: Mozilla/5.0 (Macintosh...) Chrome/135.0.0.0 Safari/537.36` (spoofed browser UA). 401/403 → "session cookie invalid/expired" error.
2. `POST https://ollama.com/api/web_search` — web search (separate feature, not quota). Header: `Authorization: Bearer <apiKey>`, `Content-Type: application/json`. Body: `{"query": string, "max_results": int}` (`OllamaSearchRequestDto`).

**Data model:** `OllamaQuota{plan: String, sessionUsage: OllamaUsageWindow?, weeklyUsage: OllamaUsageWindow?}`; `OllamaUsageWindow{usagePercent: Double, resetsAt: Instant?}`. These are NOT deserialized from JSON — parsed out of HTML via Jsoup selectors: plan from `<h2>` containing "Cloud Usage" → nested `<span class="capitalize">` (values restricted to `free`/`pro`/`max`); usage % from a `<div style="width:NN%">` progress-bar element found by walking up from a `<span class="text-sm">` labeled "Session usage"/"Weekly usage"; reset time from a `[data-time]` attribute (ISO instant).

**Quirks:** Entirely HTML-scraping based, not a JSON API — the only scrape-based parser besides none other found. Two-tier fallback for plan-badge lookup (specific h2 first, then any `span.capitalize`). Progress-bar width regex: `width:\s*([0-9.]+)%`.

## SuperGrok (xAI)

**Credential source:** OAuth 2.0 PKCE, generic flow shared with Claude/Codex via `OAuthClientConfig.forProvider(SUPERGROK)` → `xAiGrokDefaults()`. User clicks "Log in" in `SuperGrokSettingsPanel`; browser opens `authorization_endpoint = https://auth.x.ai/oauth2/authorize`, `client_id = b1a00492-073a-47ea-816f-4c329264a828`, `redirect_uri = http://127.0.0.1:56121/callback` (LOOPBACK mode — plugin runs local HTTP listener on port 56121), `scopes = "openid profile email offline_access grok-cli:access api:access"`, extra params `plan=generic&referrer=openai-usage-quota-plugin`, `includeNonce=true`. Token exchange at `https://auth.x.ai/oauth2/token`. User supplies nothing but their xAI login/consent in the browser — fully automated after that. Resulting access token stored via the shared `OAuthCredentialsStore`/PasswordSafe (not provider-specific).

**Refresh logic:** Not seen in the read files directly (handled generically by `QuotaAuthService`/`OAuthTokenClient`, out of scope here) — `fetchQuota` receives a bearer `accessToken` string already resolved.

**API calls (base `https://cli-chat-proxy.grok.com/v1/`):**
1. `GET .../billing?format=credits` — required. Headers: `Authorization: Bearer <accessToken>`, `X-XAI-Token-Auth: xai-grok-cli`, `Accept: application/json`, `User-Agent: LLM Subscription Usage`. Retried up to 2 attempts (`BILLING_REQUEST_ATTEMPTS`) on a specific "operation cancelled / Timeout expired" 400 error.
2. `GET .../settings` — optional (`required=false`), same headers, used only to pull `subscription_tier_display` for plan name.

Separate base `https://api.x.ai/v1/` for web search: `POST .../responses` — Headers: `Authorization: Bearer <accessToken>`, `Content-Type: application/json`, `User-Agent: openai-usage-quota-intellij`. Body (`GrokResponsesRequestDto`): `{model, input: [{role, content}], tools: [{type:"web_search", filters: {allowed_domains?, excluded_domains?}}], max_output_tokens}`.

**Data models:**
- `SuperGrokQuota{plan, authSource="xai-oauth-cli-proxy", creditUsage: SuperGrokUsageWindow?, onDemandCap: Long?, isUnifiedBilling: Boolean, periodType: String}`.
- `SuperGrokUsageWindow{label, used: Long, limit: Long, usagePercent: Double, resetsAt: Instant?, periodDurationMs: Long?}`.
- Billing response parsed manually (no fixed DTO) from raw `JsonObject`: reads `config.used`/`config.monthlyLimit` (or nested `{"val": N}` shape), `config.creditUsagePercent` (fallback: max of `config.productUsage[].usagePercent`, fallback: `used/limit*100`), `config.currentPeriod.{start,end,type}` or top-level `billingPeriodStart/End`, `config.isUnifiedBillingUser`, `config.onDemandCap`.

**Quirks:** Response root can be `{config:{...}}` or `{billing:{config:{...}}}` — both checked. Timeout-specific retry keyed on exact JSON `{"code":"The operation was cancelled","error":"Timeout expired"}` at HTTP 400.

## Z.ai

**Credential source:** Single API key, user pastes into `ZaiSettingsPanel` field labeled "API key:", tooltip "Z.ai API key from the Z.ai console". Stored via `ZaiApiKeyStore` in PasswordSafe, service `"Z.ai API Key"` / username `"zai-api-key"`. No OAuth, no cookie — plain static bearer key.

**No refresh logic.**

**API calls (base `https://api.z.ai/`):**
1. `GET /api/biz/subscription/list` — Headers: `Authorization: Bearer <apiKey>`, `Accept: application/json`.
2. `GET /api/monitor/usage/quota/limit` — same headers.
Both required; 401/403 → "API key invalid" error.

**Data models:**
- `ZaiSubscriptionResponseDto{code: Int?, msg: String?, data: List<ZaiSubscriptionDto>, success: Boolean?}`; `ZaiSubscriptionDto{productName, status, nextRenewTime}`.
- `ZaiQuotaResponseDto{code, msg, data: ZaiQuotaDataDto?, success}`; `ZaiQuotaDataDto{limits: List<ZaiLimitDto>}`; `ZaiLimitDto{type, unit: Int?, number: Int?, usage: Long?, currentValue: Long?, remaining: Long?, percentage: Double?, nextResetTime: Long?}`.
- Output: `ZaiQuota{plan, sessionUsage: ZaiUsageWindow?, weeklyUsage: ZaiUsageWindow?, webSearchUsage: ZaiCountUsageWindow?}`. `ZaiUsageWindow{usagePercent, resetsAt, periodDurationMs}`; `ZaiCountUsageWindow` adds `used`/`limit`.

**Quirks:** `limits[]` filtered by `type=="TOKENS_LIMIT"`, sorted by duration — shortest becomes "session", 2nd-shortest (if ≥2 entries) becomes "weekly"; `type=="TIME_LIMIT"` entry becomes web-search window. `unit` field encodes duration granularity: `1`=days, `3`=hours, `5`=minutes, `6`=weeks (`number * unit-ms`). Special "no coding plan" detection: empty subscription list + `success=false` + message containing "coding plan" or Chinese "不存在" (doesn't exist) → distinct error rather than generic failure. `percentage` field preferred over computing from `currentValue/usage` when present.