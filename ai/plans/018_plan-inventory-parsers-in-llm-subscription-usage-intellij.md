# Plan: Inventory parsers in llm-subscription-usage-intellij

## Context
User want inventory of AI-agent-usage parsers in `~/git/moritzfl/llm-subscription-usage-intellij`, as plan items — likely reference for possible reuse/comparison with this project (`ai-usage`).

Key finding: architecture differs fundamentally from `ai-usage`. That repo does NOT parse local transcript/session files (no JSONL, no SQLite). Every provider calls a **live web/API usage endpoint** with stored OAuth token or session cookie, then parses JSON (except OpenCode, custom SolidStart format). Only one local file read: Codex's `~/.codex/auth.json` (token cache, not usage data).

No code changes needed — this is inventory/knowledge gathering only.

## Plan items (parser inventory)

### 1. Claude

**Files:** `quota/claude/{ClaudeQuotaClient,ClaudeQuota,ClaudeQuotaException}.kt`, `quota/idea/auth/{OAuthCredentialsStore,OAuthClientConfig,OAuthLoginFlow,OAuthTokenClient,QuotaAuthService,QuotaTokenUtil,OAuthCredentials}.kt`

**Credential source:** Browser OAuth Authorization Code + PKCE, **paste-based callback** (Claude's redirect URI `https://platform.claude.com/oauth/code/callback` is a hosted page, not localhost — no loopback server). Config (`OAuthClientConfig.anthropicClaudeDefaults`): `clientId = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"`, `authorizationEndpoint = https://claude.ai/oauth/authorize`, `tokenEndpoint = https://platform.claude.com/v1/oauth/token`, `scopes = "org:create_api_key user:profile user:inference user:sessions:claude_code user:mcp_servers user:file_upload"`.
Plugin generates PKCE `code_verifier` (64 random bytes, base64url) + `code_challenge` (SHA-256 of verifier) + random 32-hex-char `state`, opens system browser to the authorize URL. **User must copy-paste the resulting code/state back into the plugin's login dialog** — accepted forms: full callback URL, `#code=&state=` fragment, bare `code=...&state=...`, or legacy `code#state`.
Token exchange: `POST https://platform.claude.com/v1/oauth/token`, JSON body `{grant_type: "authorization_code", client_id, code, redirect_uri, code_verifier, state}`. Result `OAuthCredentials(accessToken, refreshToken, expiresAt, accountId, hd)` — JSON-serialized into IntelliJ **PasswordSafe**, service name `"LLM Subscription Usage OAuth (claude)"`, username `"claude-oauth"`.

**Token refresh:** checks `expiresAt - 5min skew`; if expired, `POST` same token endpoint with `{grant_type: "refresh_token", client_id, refresh_token}` (JSON body). `expiresAt` = response `expires_in` if present, else JWT `exp` claim decode, else now+1h. Terminal auth failure clears stored credentials (forces re-login).

**API call:** `GET https://api.anthropic.com/api/oauth/usage`
Headers: `Authorization: Bearer <accessToken>`, `Accept: application/json`, `Content-Type: application/json`, `anthropic-beta: oauth-2025-04-20`, `User-Agent: claude-cli/2.1.87 (external, cli)` (impersonates Claude CLI).
401 → "auth expired"; 403 + body containing `"user:profile"` → missing-scope; 403 otherwise → auth expired; 429 → rate limited.

**Data model** (response `ClaudeUsageResponseDto`):
```
five_hour, seven_day, seven_day_sonnet, seven_day_opus, seven_day_oauth_apps: { utilization: Double?, resets_at: String? }
seven_day_routines, seven_day_claude_routines, claude_routines, routines, routine, seven_day_cowork, cowork: same shape (fallback chain)
extra_usage: { is_enabled, monthly_limit: Long?, used_credits: Long?, utilization: Double?, currency: String? }
limits: [ { kind, group, percent: Double?, resets_at, scope: { model: { id, display_name }, surface } } ]
```
Domain model `ClaudeQuota`: `plan, fiveHourUsage/sevenDayUsage/sevenDaySonnetUsage/sevenDayOpusUsage/sevenDayOauthAppsUsage/routinesUsage: ClaudeUsageWindow?, scopedLimits: List<ClaudeUsageWindow>, extraUsage: ClaudeExtraUsage?, fetchedAt, rawJson`.

**Quirks:** legacy field-name fallback chain for "routines" (API renamed repeatedly); scoped-limit group label derived from `group`/`kind` ("session"→5h, "weekly"→7d); scope label falls back `display_name`→`id`→`surface`; extra-usage percent computed manually from `used_credits/monthly_limit*100` if `utilization` absent; throws if response has no windows and no enabled extra-usage (guards against silent API-shape changes).

### 2. Cursor

**Files:** `quota/cursor/{CursorQuotaClient,CursorQuota,CursorSessionTokenParser,CursorAuth,CursorQuotaException}.kt`, `quota/idea/cursor/CursorCredentialsStore.kt`

**Credential source:** Fully manual, no OAuth. User opens Cursor in a browser, copies the `WorkosCursorSessionToken` cookie value, pastes it into the plugin's Cursor settings panel. Stored raw in PasswordSafe, service `"Cursor Session Cookie"`, username `"WorkosCursorSessionToken"`.
`CursorSessionTokenParser` decodes at use-time: cookie format `userId::accessToken` (URL-encoded as `userId%3A%3AaccessToken`). `extractAccessToken` URL-decodes, splits on `::`, takes the JWT after the separator (or the whole value if it starts with `eyJ`). No refresh logic, no expiry tracking — user must re-paste on 401.

**API calls** (two paths, tried in order):
1. Web path (if session cookie present): `GET https://cursor.com/api/usage-summary`, `GET https://cursor.com/api/auth/me` (best-effort, for `sub`/email), `GET https://cursor.com/api/usage?user=<urlencoded userId>` — all with header `Cookie: WorkosCursorSessionToken=<token>`, `Accept: application/json`.
2. Fallback gRPC-JSON path (`api2.cursor.sh`): `POST /aiserver.v1.DashboardService/GetCurrentPeriodUsage` (body `"{}"`), `POST /aiserver.v1.DashboardService/GetPlanInfo` (best-effort), `GET /auth/full_stripe_profile` (best-effort) — all with `Authorization: Bearer <accessToken>` (JWT from cookie), `Content-Type: application/json`, plus `Cookie` header if present.

**Data models:**
```
Web: UsageSummaryResponse { billingCycleStart/End, membershipType, limitType, isUnlimited,
  autoModelSelectedDisplayMessage, namedModelSelectedDisplayMessage,
  individualUsage { plan: {enabled,used,limit,remaining,breakdown,autoPercentUsed,apiPercentUsed,totalPercentUsed}, onDemand/overall: {enabled,used,limit,remaining} },
  teamUsage { onDemand/pooled: same budget shape } }
UserInfoResponse { email, name, sub, email_verified }
RequestUsageResponse { "gpt-4": {numRequests,numRequestsTotal,numTokens,maxRequestUsage,maxTokenUsage}, startOfMonth }

Dashboard: CurrentPeriodUsageResponse { billingCycleStart/End,
  planUsage: {totalSpend,includedSpend,bonusSpend,limit,autoPercentUsed,apiPercentUsed,totalPercentUsed},  // cents
  spendLimitUsage: {totalSpend,pooledLimit,pooledUsed,pooledRemaining,individualUsed,limitType},
  displayThreshold, displayMessage, autoModelSelectedDisplayMessage, namedModelSelectedDisplayMessage }
PlanInfoResponse { planInfo: {planName,includedAmountCents,price,billingCycleEnd} }
StripeProfileResponse { membershipType, isTeamMember }
```
Domain model `CursorQuota`: `planName, email, membershipType, planUsage?, spendLimit?, onDemandUsage?, teamOnDemandUsage?, requestUsage?, displayMessage, autoModelDisplayMessage, apiModelDisplayMessage`.

**Quirks:** web path tried first, silently swallowed (`runCatching`) before falling back to gRPC-JSON dashboard path; money fields are in **cents** (Double) across both paths, divided by 100.0 everywhere; `normalizeRawJson` unwraps double-JSON-encoded string fields; `parseTimestamp` heuristically detects epoch seconds/millis/micros by magnitude, falls back to ISO-8601; confirmed no local `state.vscdb` SQLite read.

### 3. GitHub Copilot

**Files:** `quota/github/{GitHubQuotaClient,GitHubQuota,GitHubOAuthClient,GitHubQuotaException}.kt`, `quota/idea/github/{GitHubAuthService,GitHubCredentialsStore}.kt`

**Credential source:** GitHub OAuth 2.0 **Device Authorization Grant (RFC 8628)** — automated except user must open a browser to `https://github.com/login/device` and type a short code shown by the plugin. Public device-flow client id `Ov23li8tweQw6odWQebz`, no client secret. Scope: `read:user`.
Flow: `POST https://github.com/login/device/code` (form `client_id=<id>&scope=read:user`) → `device_code, user_code, verification_uri, expires_in, interval`. Plugin opens `verification_uri` in browser, shows `user_code` to user. Polls `POST https://github.com/login/oauth/access_token` (form `client_id=<id>&device_code=<code>&grant_type=urn:ietf:params:oauth:grant-type:device_code`) handling `authorization_pending`/`slow_down` (+5s backoff)/`expired_token`/`access_denied`, at `interval` (default 5s) until `expires_in` (default 900s). **Device-flow token never expires and has no refresh token.**
Result `GitHubCredentials(accessToken, oauthClientId)` stored as JSON in PasswordSafe, service `"GitHub Copilot Credentials"`, username `"github-copilot-credentials"`.

**API call:** `GET https://api.github.com/copilot_internal/user` (or `https://api.<enterpriseHost>/copilot_internal/user` for GHE)
Headers: `Authorization: token <accessToken>` (note: `token` scheme, not `Bearer`), `Accept: application/json`, `User-Agent: openai-usage-quota-intellij`, `Copilot-Integration-Id: JetBrainsIDE`.
401/403 → "session expired"; 404 → "no Copilot subscription found".

**Data model** (`GitHubUserResponseDto`):
```
copilot_plan, access_type_sku: String?
chat_enabled, cli_enabled: Boolean?
quota_reset_date: String?
quota_snapshots: { premium_interactions, chat, completions: { entitlement, quota_total, remaining, quota_remaining, percent_remaining: Double?, unlimited: Boolean? } }
limited_user_reset_date: String?
limited_user_quotas: { chat: Long?, completions: Long? }
monthly_quotas: { chat: Long?, completions: Long? }
```
Domain model `GitHubQuota`: `plan, subscriptionState (ACTIVE/SUBSCRIPTION_ENDED/NO_ACTIVE_SUBSCRIPTION), premiumInteractions/chat/completions: GitHubUsageWindow?`.

**Quirks:** paid plans report `quota_snapshots` (percentage-based); free tier instead reports `limited_user_quotas` absolute counters vs `monthly_quotas` max — client falls back between shapes per field; `unlimited: true` snapshots kept in model but excluded from usage-percent aggregation; reset dates are plain dates (`"2026-07-01"`), parsed as `Instant.parse` then `"${value}T00:00:00Z"` fallback; `subscriptionState` derived heuristically from `access_type_sku`/`chat_enabled`/`cli_enabled`/quota-payload presence.

### 4. OpenAI Codex

**Files:** `quota/openai/{OpenAiCodexQuotaClient,OpenAiCodexQuota,OpenAiCodexQuotaException,OpenAiCodexQuotaSerializer,OpenAiCredits,UsageWindow,RateLimitResetCredit}.kt`, `quota/openai/dto/{CreditsDto,OAuthTokenResponseDto,OpenAiAuthorizationDto,RateLimitDto,UsageResponseDto,UsageWindowDto}.kt`, `proxy/auth/{AuthLoader,AuthFileResolver}.kt`, `proxy/util/JwtParser.kt`

**Credential source:** File read, not user-pasted. `AuthLoader.loadAuthTokens()` resolves candidate paths via `AuthFileResolver.resolveCandidates()`: env `CHATGPT_LOCAL_HOME`/`auth.json`, env `CODEX_HOME`/`auth.json`, `~/.chatgpt-local/auth.json`, `~/.codex/auth.json` (first existing file wins). Expected JSON shape: `{tokens: {access_token, id_token, refresh_token, account_id}, last_refresh}`. If `account_id` absent, derived from `id_token` JWT claim `https://api.openai.com/auth.chatgpt_account_id` via `JwtParser.deriveAccountId()`. User must have already run `codex login` externally — plugin never prompts for token input, only reads what Codex CLI wrote.

**Token refresh:** `shouldRefreshAccessToken()` triggers refresh if access-token JWT `exp` is within 5min (`REFRESH_EXPIRY_MARGIN_MS`) of expiring, or `last_refresh` older than 55min (`REFRESH_INTERVAL_MS`), or token missing. Refresh: `POST {issuer}/oauth/token` (issuer default `ServerConfig.DEFAULT_ISSUER`, override via `CHATGPT_LOCAL_ISSUER` env) JSON body `{grant_type: "refresh_token", refresh_token, client_id, scope: "openid profile email offline_access"}` (`client_id` default `ServerConfig.DEFAULT_CLIENT_ID` or env `CHATGPT_LOCAL_CLIENT_ID`). On success, rewrites `auth.json` atomically (temp file, `chmod 600`/Windows ACL owner-only, `ATOMIC_MOVE`).

**API calls:**
- `GET https://chatgpt.com/backend-api/wham/usage` — `Authorization: Bearer <accessToken>`, `Accept: application/json`, optional `ChatGPT-Account-Id: <accountId>`.
- `GET https://chatgpt.com/backend-api/wham/rate-limit-reset-credits` — same headers.
- `POST https://chatgpt.com/backend-api/wham/rate-limit-reset-credits/consume` — same headers + `Content-Type: application/json`; body `{credit_id, redeem_request_id: <random UUID>}`.

**Data models:**
```
UsageResponseDto { user_id, account_id, email, rate_limit: RateLimitDto?, code_review_rate_limit: RateLimitDto?,
  plan_type, credits: CreditsDto?, spend_control: SpendControlDto?,
  rate_limit_reached_type: RateLimitReachedTypeDto?, rate_limit_reset_credits: RateLimitResetCredits?,
  additional_rate_limits: List<AdditionalRateLimitDto>? }
RateLimitDto { allowed, limit_reached: Boolean?, primary_window/secondary_window: UsageWindowDto? }
UsageWindowDto { used_percent: Double?, limit_window_seconds: Double?, reset_at: Double? }  // epoch seconds
CreditsDto { has_credits, unlimited, overage_limit_reached, balance: String?, approx_local_messages/approx_cloud_messages: List<Int>? }
SpendControlDto { reached: Boolean?, individual_limit: Double? }
RateLimitReachedTypeDto { type, details }
AdditionalRateLimitDto { limit_name, metered_feature, rate_limit: RateLimitDto? }
```
Domain `OpenAiCodexQuota`: `primary/secondary/reviewPrimary/reviewSecondary: UsageWindow?, planType, allowed, limitReached, reviewAllowed, reviewLimitReached, accountId, email, credits, spendControl, rateLimitReachedType, resetCreditsAvailableCount: Int, resetCredits: List<RateLimitResetCredit>, extraRateLimits: List<OpenAiExtraRateLimit>, fetchedAt, rawJson`.

**Quirks:** `AdditionalRateLimitDto.displayTitle()` strips `gpt-<version>-` prefixes, title-cases feature names; window naming buckets duration into "5-hour"/"Weekly"/"Monthly" by comparing seconds with 60s tolerance. `toString()` redacts `rawJson`/`accountId`/`email`. Reset-credits endpoint failures swallowed (`runCatching{}.getOrDefault(...)`) rather than thrown.

### 5. Kimi (Moonshot)

**Files:** `quota/kimi/{KimiQuotaClient,KimiQuota,KimiDeviceHeaders,KimiWebSearchClient,KimiOAuthClient,KimiCredentialRefresher,KimiQuotaException}.kt`, `quota/idea/kimi/{KimiAuthService,KimiCredentialsStore}.kt`

**Credential source:** Fully automated OAuth 2.0 Device Authorization Grant — no manual paste. `KimiOAuthClient.requestDeviceAuthorization()` → `POST https://auth.kimi.com/api/oauth/device_authorization` (form `client_id=17e5f671-d194-4dfb-9706-5516cb48c098`) returns `user_code, device_code, verification_uri(_complete), expires_in, interval`. User opens verification URL, approves; plugin polls `POST https://auth.kimi.com/api/oauth/token` (form `client_id, device_code, grant_type=urn:ietf:params:oauth:grant-type:device_code`) until `access_token` returned (handles `authorization_pending`/`slow_down`/`expired_token`). Resulting `KimiCredentials{accessToken, refreshToken, expiresAtEpochSeconds, scope, tokenType}` JSON-serialized into PasswordSafe, `CredentialAttributes("Kimi Credentials", "kimi-credentials")`.

**Device fingerprint:** every OAuth request sends `KimiDeviceHeaders.all()`: `X-Msh-Platform: kimi_cli`, `X-Msh-Version: 1.40.0`, `X-Msh-Device-Name` (hostname), `X-Msh-Device-Model` (OS+version+arch), `X-Msh-Os-Version`, `X-Msh-Device-Id` (random UUID persisted in `PropertiesComponent` key `kimi.oauth.device.id`).

**Token refresh:** `KimiCredentialRefresher.refreshIfNeeded()`/`refresh()` — proactive refresh before request, reactive re-fetch once on 401/403 via same `https://auth.kimi.com/api/oauth/token` endpoint (presumably `grant_type=refresh_token`), throws `KimiQuotaException("Session expired...")` if refresh also fails.

**API call:** `GET https://api.kimi.com/coding/v1/usages` — `Authorization: Bearer <accessToken>`, `Accept: application/json`.

**Data models:**
```
KimiUsageResponseDto { usage: KimiLimitDetailDto?, limits: List<KimiLimitDto>, user: KimiUserDto? }
KimiLimitDto { window: KimiWindowDto?, detail: KimiLimitDetailDto? }
KimiWindowDto { duration: Long?, timeUnit: String? }  // TIME_UNIT_MINUTE/_HOUR/_DAY
KimiLimitDetailDto { limit: String?, remaining: String?, resetTime: String? }  // limit/remaining are STRINGS
KimiUserDto.membership: KimiMembershipDto? -> { level: String? }  // LEVEL_INTERMEDIATE/_ADVANCED/_PREMIUM
```
Domain `KimiQuota{plan, sessionUsage: KimiUsageWindow?, totalUsage: KimiUsageWindow?, fetchedAt, rawJson}`; `KimiUsageWindow{used: Long, limit: Long, usagePercent: Double, resetsAt: Instant?, periodDurationMs: Long?}`.

**Quirks:** session window = limit whose `window.duration==300 && timeUnit=="TIME_UNIT_MINUTE"` (5-min window), fallback `limits.firstOrNull()`. `used` computed as `limit - remaining` clamped ≥0. Membership level normalized to display plan name (e.g. `LEVEL_ADVANCED` → "Kimi Code Advanced").

### 6. MiniMax

**Files:** `quota/minimax/{MiniMaxQuotaClient,MiniMaxQuota,MiniMaxWebSearchClient,MiniMaxQuotaException}.kt`, `quota/idea/minimax/MiniMaxApiKeyStore.kt`

**Credential source:** Direct user input — raw API key pasted into `JBPasswordField` in `MiniMaxSettingsPanel` ("API key:"), saved via `MiniMaxApiKeyStore.save()` into PasswordSafe `CredentialAttributes("MiniMax API Key", "minimax-api-key")` as plain string (not JSON-wrapped). No OAuth, no file read. Settings panel also lets user pick `MiniMaxRegionPreference` (Global vs CN) via combo box, persisted in `QuotaSettingsState`.

**Token refresh:** None — static API key.

**API calls:** region-dependent fallback list, tried in order, stops on 401/403:
- Global: `https://api.minimax.io/v1/api/openplatform/coding_plan/remains`, then `.../v1/coding_plan/remains`, then `https://www.minimax.io/v1/api/openplatform/coding_plan/remains`.
- CN: `https://api.minimaxi.com/v1/api/openplatform/coding_plan/remains`, then `.../v1/coding_plan/remains`.
Headers each attempt: `Authorization: Bearer <apiKey>`, `Content-Type: application/json`, `Accept: application/json`.

**Data models:**
```
MiniMaxResponseDto { base_resp: MiniMaxBaseRespDto?, model_remains: List<MiniMaxRemainDto> }
MiniMaxBaseRespDto { status_code: Int?, status_msg: String? }  // 0 = success
MiniMaxRemainDto { current_interval_total_count, current_interval_usage_count, current_interval_used_count,
  current_interval_remaining_count, current_interval_remains_count: Long?,
  start_time, end_time, remains_time: Long?, current_subscribe_title, plan_name, plan: String? }
```
Domain `MiniMaxQuota{plan, region: MiniMaxRegion, sessionUsage: MiniMaxUsageWindow, fetchedAt, rawJson}`.

**Quirks:** three candidate field names for remaining/used counts tried in priority order (`current_interval_usage_count` → `_remaining_count` → `_remains_count`); `used` derived as `total - remaining` if no explicit used-count. `epochSecondsOrMillis()` heuristic (value <10bn = seconds). Plan name inferred from numeric quota limit via hardcoded per-region tables when API omits plan string; region suffix " (GLOBAL)" appended to display name.

### 7. Ollama (cloud/turbo quota)

**Files:** `quota/ollama/{OllamaQuotaClient,OllamaQuota,OllamaWebSearchClient,OllamaQuotaException}.kt`, `quota/idea/ollama/{OllamaApiKeyStore,OllamaSessionCookieStore}.kt`

**Credential source:** Three separate secrets, all pasted by user into `OllamaSettingsPanel`, stored in PasswordSafe:
- Session cookie `__Secure-session` (required) — label "Session cookie (__Secure-session):", helper "Extract from ollama.com → DevTools → Storage → Cookies." Service `"Ollama Session Cookie"` / user `"ollama-session"`.
- `cf_clearance` cookie (optional, helps bypass Cloudflare) — service `"Ollama CF Clearance"` / user `"ollama-cf"`.
- API key (used only for MCP web-search/proxy, NOT quota fetch) — from `ollama.com/settings/keys` — service `"Ollama API Key"` / user `"ollama-api-key"`.
No OAuth. `@Service(APP)` singletons wrap `PasswordSafe.instance.get/set`, async-loaded off EDT with atomic generation counter.

**No token refresh** — cookie static until re-pasted.

**API calls:**
1. `GET https://ollama.com/settings` — quota fetch, **HTML scraped with Jsoup, not JSON**. Headers: `Cookie: __Secure-session=<sessionCookie>[; cf_clearance=<cfClearance>]`, `Accept: text/html`, spoofed `User-Agent: Mozilla/5.0 (Macintosh...) Chrome/135.0.0.0 Safari/537.36`. 401/403 → invalid/expired.
2. `POST https://ollama.com/api/web_search` — `Authorization: Bearer <apiKey>`, `Content-Type: application/json`; body `{"query": string, "max_results": int}`.

**Data model:** `OllamaQuota{plan: String, sessionUsage: OllamaUsageWindow?, weeklyUsage: OllamaUsageWindow?}`; `OllamaUsageWindow{usagePercent: Double, resetsAt: Instant?}` — parsed from HTML, not JSON: plan from `<h2>` "Cloud Usage" → nested `<span class="capitalize">` (free/pro/max); usage % from `<div style="width:NN%">` progress-bar found by walking up from `<span class="text-sm">` labeled "Session usage"/"Weekly usage"; reset time from `[data-time]` attribute (ISO instant).

**Quirks:** only HTML-scraping-based parser in the repo (everything else is JSON). Two-tier fallback for plan-badge lookup. Progress-bar regex `width:\s*([0-9.]+)%`.

### 8. SuperGrok (xAI)

**Files:** `quota/supergrok/{SuperGrokQuotaClient,SuperGrokQuota,SuperGrokImagineClient,SuperGrokWebSearchClient,SuperGrokQuotaException}.kt`

**Credential source:** OAuth 2.0 PKCE, generic flow shared with Claude/Codex via `OAuthClientConfig.forProvider(SUPERGROK)` → `xAiGrokDefaults()`. User clicks "Log in"; browser opens `authorization_endpoint = https://auth.x.ai/oauth2/authorize`, `client_id = b1a00492-073a-47ea-816f-4c329264a828`, `redirect_uri = http://127.0.0.1:56121/callback` (**loopback** — plugin runs local HTTP listener on port 56121, unlike Claude's paste-based callback), `scopes = "openid profile email offline_access grok-cli:access api:access"`, extra params `plan=generic&referrer=openai-usage-quota-plugin`, `includeNonce=true`. Token exchange `POST https://auth.x.ai/oauth2/token`. User supplies nothing but xAI login/consent in browser — fully automated after that. Token stored via shared `OAuthCredentialsStore`/PasswordSafe.

**Token refresh:** handled generically by shared `QuotaAuthService`/`OAuthTokenClient` (not SuperGrok-specific) — `fetchQuota` receives an already-resolved bearer `accessToken`.

**API calls** (base `https://cli-chat-proxy.grok.com/v1/`):
1. `GET .../billing?format=credits` (required) — `Authorization: Bearer <accessToken>`, `X-XAI-Token-Auth: xai-grok-cli`, `Accept: application/json`, `User-Agent: LLM Subscription Usage`. Retried up to 2 attempts on a specific "operation cancelled / Timeout expired" 400 error.
2. `GET .../settings` (optional) — same headers, pulls `subscription_tier_display` for plan name.

Separate base `https://api.x.ai/v1/` for web search: `POST .../responses` — `Authorization: Bearer <accessToken>`, `Content-Type: application/json`, `User-Agent: openai-usage-quota-intellij`; body `{model, input: [{role, content}], tools: [{type:"web_search", filters: {allowed_domains?, excluded_domains?}}], max_output_tokens}`.

**Data models:**
```
SuperGrokQuota { plan, authSource="xai-oauth-cli-proxy", creditUsage: SuperGrokUsageWindow?, onDemandCap: Long?, isUnifiedBilling: Boolean, periodType: String }
SuperGrokUsageWindow { label, used: Long, limit: Long, usagePercent: Double, resetsAt: Instant?, periodDurationMs: Long? }
```
Billing response parsed manually (no fixed DTO) from raw `JsonObject`: `config.used`/`config.monthlyLimit` (or nested `{"val": N}`), `config.creditUsagePercent` (fallback: max of `config.productUsage[].usagePercent`, fallback: `used/limit*100`), `config.currentPeriod.{start,end,type}` or top-level `billingPeriodStart/End`, `config.isUnifiedBillingUser`, `config.onDemandCap`.

**Quirks:** response root can be `{config:{...}}` or `{billing:{config:{...}}}` — both checked. Timeout-specific retry keyed on exact JSON `{"code":"The operation was cancelled","error":"Timeout expired"}` at HTTP 400.

### 9. Z.ai

**Files:** `quota/zai/{ZaiQuotaClient,ZaiQuota,ZaiWebSearchClient,ZaiQuotaException}.kt`, `quota/idea/zai/ZaiApiKeyStore.kt`

**Credential source:** Single API key, user pastes into `ZaiSettingsPanel` ("API key:", tooltip "Z.ai API key from the Z.ai console"). Stored via `ZaiApiKeyStore` in PasswordSafe, service `"Z.ai API Key"` / user `"zai-api-key"`. No OAuth, no cookie.

**No refresh logic.**

**API calls** (base `https://api.z.ai/`), both required, headers `Authorization: Bearer <apiKey>`, `Accept: application/json`; 401/403 → "API key invalid":
1. `GET /api/biz/subscription/list`
2. `GET /api/monitor/usage/quota/limit`

**Data models:**
```
ZaiSubscriptionResponseDto { code: Int?, msg: String?, data: List<ZaiSubscriptionDto>, success: Boolean? }
ZaiSubscriptionDto { productName, status, nextRenewTime }
ZaiQuotaResponseDto { code, msg, data: ZaiQuotaDataDto?, success }
ZaiQuotaDataDto { limits: List<ZaiLimitDto> }
ZaiLimitDto { type, unit: Int?, number: Int?, usage: Long?, currentValue: Long?, remaining: Long?, percentage: Double?, nextResetTime: Long? }
```
Output `ZaiQuota{plan, sessionUsage: ZaiUsageWindow?, weeklyUsage: ZaiUsageWindow?, webSearchUsage: ZaiCountUsageWindow?}`.

**Quirks:** `limits[]` filtered by `type=="TOKENS_LIMIT"`, sorted by duration — shortest → "session", 2nd-shortest (if ≥2) → "weekly"; `type=="TIME_LIMIT"` entry → web-search window. `unit` encodes granularity: `1`=days, `3`=hours, `5`=minutes, `6`=weeks (`number * unit-ms`). "No coding plan" detected via empty subscription list + `success=false` + message containing "coding plan" or Chinese "不存在". `percentage` field preferred over computing from `currentValue/usage` when present.

10. **OpenCode (Go/Zen)** — `src/main/kotlin/de/moritzf/quota/opencode/{OpenCodeQuotaClient,OpenCodeQuota,SolidStartValueParser}.kt` (396 lines, largest parser overall). Custom hand-rolled recursive-descent parser for SolidStart RPC wire format (non-JSON: `!0`/`!1` booleans, `new Date(...)`, `$R[n]` back-references). Only non-JSON wire format in repo.

11. **OpenCode Zen proxy variant** — `src/main/kotlin/de/moritzf/quota/opencode/proxy/OpenCodeZenSubscriptionProxyProvider.kt`. Wraps OpenCode credentials for local proxy, reuses `OpenCodeQuotaClient`.

12. **Shared infra** (not providers, but load-bearing): `quota/shared/{JsonSupport,ProviderQuota}.kt`, `quota/idea/common/{QuotaProviderRegistry,QuotaProviderType,QuotaUsageService,QuotaSnapshotCache}.kt`, `proxy/util/JwtParser.kt` (generic JWT claim decode, no sig verify), `proxy/auth/AuthManager.kt`.

## Not present in that repo
No local transcript/session-log parsing (`~/.claude/projects/**/*.jsonl`, Cursor SQLite, Codex rollout files), no token-cost calculation, no pricing tables. Everything is vendor-reported usage percentages via live API — contrasts with `ai-usage`'s likely local-log-parsing approach.

## Verification
None needed — read-only inventory task, no code written.
