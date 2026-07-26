Confirmed: no email/username field anywhere in Kimi's flow — the `KimiUserDto` only has `membership.level`, and no JWT decoding occurs. All research gathered. Compiling final report.

## Findings

### 1. Cursor (`quota/cursor/`, `quota/idea/cursor/`)

**Credential storage** (`idea/cursor/CursorCredentialsStore.kt`): PasswordSafe `CredentialAttributes(SESSION_SERVICE_NAME="Cursor Session Cookie", SESSION_USER_NAME="WorkosCursorSessionToken")`. Stores the **raw browser cookie value** (not split into fields) as `Credentials(SESSION_USER_NAME, normalized)`.

**`WorkosCursorSessionToken`** (`CursorSessionTokenParser.kt`): `const val COOKIE_NAME = "WorkosCursorSessionToken"` — this **is** the literal browser cookie name. Format: `userId::accessToken`, URL-encoded as `userId%3A%3AaccessToken` (`SEPARATOR = "::"`). Access token is a JWT starting with `"eyJ"` (checked via `decoded.startsWith("eyJ")` as fallback if no separator found). `extractAccessToken`: URL-decode → find `"::"` → substring after it, trimmed. `extractUserId`: substring before `"::"`. `buildCookieHeader(sessionToken)` returns literally `"$COOKIE_NAME=${sessionToken.trim()}"` i.e. `"WorkosCursorSessionToken=<value>"`.

**Requests** (`CursorQuotaClient.kt`):
- `DEFAULT_BASE_URI = "https://api2.cursor.sh"`, `DEFAULT_WEB_BASE_URI = "https://cursor.com"`.
- Bearer-token flow (no session cookie): POST `https://api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage` and `.../GetPlanInfo`, body `"{}"`, headers `Authorization: Bearer $accessToken`, `Content-Type: application/json` (plus `Cookie` header if session cookie also present). GET `https://api2.cursor.sh/auth/full_stripe_profile`.
- Cookie flow (preferred if `sessionCookie` present): GET `https://cursor.com/api/usage-summary`, GET `https://cursor.com/api/auth/me`, GET `https://cursor.com/api/usage?user=<urlencoded userId>` — all with header `Cookie: WorkosCursorSessionToken=<token>` and `Accept: application/json`. `userId` resolved from `/api/auth/me`'s `sub` field, or falls back to `CursorSessionTokenParser.extractUserId`.
- 401/403 → error message: `"Cursor session is invalid or expired. Update WorkosCursorSessionToken in settings."`

**Exact JSON field names** (private data classes in `CursorQuotaClient.kt`):
- `CurrentPeriodUsageResponse`: `billingCycleStart`, `billingCycleEnd`, `planUsage` (→`PlanUsageResponse`: `totalSpend`, `includedSpend`, `bonusSpend`, `limit`, `autoPercentUsed`, `apiPercentUsed`, `totalPercentUsed`), `spendLimitUsage` (→`SpendLimitUsageResponse`: `totalSpend`, `pooledLimit`, `pooledUsed`, `pooledRemaining`, `individualUsed`, `limitType`), `displayThreshold`, `displayMessage`, `autoModelSelectedDisplayMessage`, `namedModelSelectedDisplayMessage`.
- `PlanInfoResponse`: `planInfo` → `PlanInfoDetails{planName, includedAmountCents, price, billingCycleEnd}`.
- `StripeProfileResponse`: `membershipType`, `isTeamMember` (`@SerialName("isTeamMember")`).
- `UsageSummaryResponse` (web/cookie path): `billingCycleStart`, `billingCycleEnd`, `membershipType`, `limitType`, `isUnlimited`, `autoModelSelectedDisplayMessage`, `namedModelSelectedDisplayMessage`, `individualUsage`→`IndividualUsageResponse{plan: UsageSummaryPlanResponse{enabled,used,limit,remaining,breakdown{included,bonus,total},autoPercentUsed,apiPercentUsed,totalPercentUsed}, onDemand: UsageBudgetResponse, overall: UsageBudgetResponse}`, `teamUsage`→`TeamUsageResponse{onDemand, pooled: UsageBudgetResponse}`. `UsageBudgetResponse{enabled,used,limit,remaining}`.
- `RequestUsageResponse`: field `@SerialName("gpt-4") val gpt4` → `CursorModelUsageResponse{numRequests, numRequestsTotal, numTokens, maxRequestUsage, maxTokenUsage}`; also `startOfMonth`.
- `UserInfoResponse` (from `/api/auth/me`): `email`, `name`, `sub`, `@SerialName("email_verified") emailVerified`.

Monetary values are in **cents** (divide by 100.0 → USD) throughout.

### 2. Ollama (`quota/ollama/`, `quota/idea/ollama/`)

**Cookies** (`idea/ollama/OllamaSessionCookieStore.kt` + `OllamaQuotaClient.kt`): literal cookie names built in `buildCookieHeader`:
```
"__Secure-session=$sessionCookie"; optionally "cf_clearance=$cfClearance"
```
joined with `"; "`. PasswordSafe keys: `SESSION_SERVICE_NAME="Ollama Session Cookie"`/`SESSION_USER_NAME="ollama-session"`, `CF_SERVICE_NAME="Ollama CF Clearance"`/`CF_USER_NAME="ollama-cf"` (separate `OllamaApiKeyStore` also exists: service `"Ollama API Key"`, user `"ollama-api-key"`).

**Request**: GET `https://ollama.com/settings` (`DEFAULT_ENDPOINT`), headers `Cookie: <built above>`, `Accept: text/html`, `User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36`.

**HTML scraping** (Jsoup, in `OllamaQuotaClient.kt` companion):
- Plan: `PLAN_VALUES = setOf("free", "pro", "max")`. Select `h2:contains(Cloud Usage)` → within it `span.capitalize` → `.text().trim().lowercase()`, checked against `PLAN_VALUES`. Fallback: iterate `span[class~=capitalize]` across whole doc.
- Usage windows: labels are literal text `"Session usage"` and `"Weekly usage"`. Selector: `doc.select("span.text-sm")`, filtered where `.text().trim() == label`.
- From the label span, walk **up** parents (`labelSpan.parent()`, then `.parent()` repeatedly) until an ancestor contains both `div[style*=width:]` AND `[data-time]` (via `selectFirst`) — that ancestor is the "usage window block".
- Percent bar: `windowBlock.select("div[style*=width:]").first()`, then regex `Regex("""width:\s*([0-9.]+)%""")` against the `style` attribute, group 1 → `usagePercent`.
- Reset time: `windowBlock.select("[data-time]").first()?.attr("data-time")` parsed as ISO `Instant.parse`.
- If both session and weekly usage are null → throws with message `"Could not parse Ollama quota from HTML..."`.
- 401/403 → `"Ollama session cookie is invalid or expired (HTTP $status). Please update your session cookie in the plugin settings."`

### 3. SuperGrok (`quota/supergrok/`)

**Base URI**: `DEFAULT_BASE_URI = "https://cli-chat-proxy.grok.com/v1/"`.
**Endpoints**: `WEEKLY_BILLING_PATH = "billing?format=credits"` (required), `SETTINGS_PATH = "settings"` (optional).
**Headers on every request**: `Authorization: Bearer $accessToken`, `X-XAI-Token-Auth: xai-grok-cli` (`TOKEN_AUTH_HEADER`), `Accept: application/json`, `User-Agent: LLM Subscription Usage`. `AUTH_SOURCE = "xai-oauth-cli-proxy"` (stored as metadata, not sent).
**Retry**: `BILLING_REQUEST_ATTEMPTS = 2`; retries once if `status==400` and JSON body has `code == "The operation was cancelled"` and `error == "Timeout expired"` (case-insensitive) — `isGrokBillingTimeout`.

**Field names parsed** (dynamic JsonObject walk, not fixed DTOs) — from `billing?format=credits` response:
- Root: `config` object, OR `billing.config` (fallback path `root.objectValue("billing")?.objectValue("config")`).
- Within `config`: `used` (or `{"val": N}` wrapper — see `unitValue`), `monthlyLimit`, `creditUsagePercent` (Double, preferred over computed), `productUsage` (JsonArray of objects each with `usagePercent`, max taken), `currentPeriod` (object with `start`, `end`, `type`), `billingPeriodStart`/`billingPeriodEnd` (fallback to `currentPeriod.start/end`), `isUnifiedBillingUser` (Boolean), `onDemandCap`.
- From `/settings` response: top-level string field `subscription_tier_display` → used as `plan`.
- `unitValue(name)`: tries `this[name]` as `JsonPrimitive.longOrNull`, else `(this[name] as JsonObject)["val"]` as long — i.e. numeric fields can be either a raw number or `{"val": N}`.

**PKCE/OAuth constants** (`idea/auth/OAuthClientConfig.kt`, function `xAiGrokDefaults()`):
```
clientId = "b1a00492-073a-47ea-816f-4c329264a828"
authorizationEndpoint = "https://auth.x.ai/oauth2/authorize"
tokenEndpoint = "https://auth.x.ai/oauth2/token"
redirectUri = "http://127.0.0.1:56121/callback"
scopes = "openid profile email offline_access grok-cli:access api:access"
callbackPort = 56121
extraParameters = {"plan": "generic", "referrer": "openai-usage-quota-plugin"}
includeNonce = true
```
Uses standard PKCE (`OAuthLoginFlow.start` generates verifier/challenge) plus a local loopback HTTP callback server on port 56121, form-encoded token exchange (default `tokenBodyFormat = FORM`).

### 4. Kimi (`quota/kimi/`)

**Device-flow OAuth** (`KimiOAuthClient.kt`): `CLIENT_ID = "17e5f671-d194-4dfb-9706-5516cb48c098"`, `OAUTH_HOST = "https://auth.kimi.com"`. Endpoints: POST `/api/oauth/device_authorization` (form body `client_id`), POST `/api/oauth/token` (form body `client_id`, `device_code`, `grant_type=urn:ietf:params:oauth:grant-type:device_code`). Response DTO fields (snake_case via `@SerialName`): `user_code`, `device_code`, `verification_uri`, `verification_uri_complete`, `expires_in`, `interval`; token DTO: `access_token`, `refresh_token`, `expires_in`, `scope`, `token_type`, `error`, `error_description`. Poll results: `authorization_pending`/`slow_down` → keep polling; `expired_token` → throw.

**Refresh** (`KimiCredentialRefresher.kt`): same `CLIENT_ID`, `TOKEN_ENDPOINT = "https://auth.kimi.com/api/oauth/token"`, form POST `grant_type=refresh_token`, `refresh_token`, `client_id`. `REFRESH_BUFFER_SECONDS = 300L`.

**Device headers** (`KimiDeviceHeaders.kt`) sent on every OAuth POST: `X-Msh-Platform: "kimi_cli"`, `X-Msh-Version: "1.40.0"`, `X-Msh-Device-Name` (sanitized ASCII hostname), `X-Msh-Device-Model` (e.g. `"macOS 14.5 aarch64"` built via `buildModel(os, version, arch)`), `X-Msh-Os-Version`, `X-Msh-Device-Id` (persisted random UUID, dashes stripped, stored in IntelliJ `PropertiesComponent` under key `kimi.oauth.device.id`).

**Usage endpoint** (`KimiQuotaClient.kt`): GET `https://api.kimi.com/coding/v1/usages`, header `Authorization: Bearer $accessToken`, `Accept: application/json` (no `X-Msh-*` headers on this call — only OAuth calls send them).

**Exact JSON DTOs**:
- `KimiUsageResponseDto { usage: KimiLimitDetailDto?, limits: List<KimiLimitDto> = [], user: KimiUserDto? }`
- `KimiLimitDto { window: KimiWindowDto?, detail: KimiLimitDetailDto? }`
- `KimiWindowDto { duration: Long?, timeUnit: String? }` — values seen: `"TIME_UNIT_MINUTE"`, `"TIME_UNIT_HOUR"`, `"TIME_UNIT_DAY"`.
- `KimiLimitDetailDto { limit: String?, remaining: String?, resetTime: String? }` — **limit/remaining are strings**, parsed via `toLongOrNull()`; `used = limit - remaining`.
- `KimiUserDto { membership: KimiMembershipDto? }`, `KimiMembershipDto { level: String? }` — values: `"LEVEL_INTERMEDIATE"`, `"LEVEL_ADVANCED"`, `"LEVEL_PREMIUM"` mapped to `"Kimi Code Intermediate/Advanced/Premium"`; else `"Kimi Code " + level.removePrefix("LEVEL_").lowercase().capitalize()`.
- Session-window selection: `dto.limits.firstOrNull { it.window?.duration == 300L && it.window.timeUnit == "TIME_UNIT_MINUTE" }` (i.e. the 5-minute window) or first limit as fallback.

**Email/identity**: confirmed **no email or username field exists anywhere** in the Kimi flow — `KimiUserDto` only carries `membership.level`. No JWT decoding of the access token occurs anywhere in `kimi/` or `idea/kimi/` (grepped for `email`, `username`, `jwt`, `decode` — only JSON `decodeFromString` calls, no identity fields). There is no endpoint that returns Kimi user email/username in this codebase.

All file paths referenced are under `~/git/moritzfl/llm-subscription-usage-intellij/src/main/kotlin/de/moritzf/quota/` (and `idea/` subpackage for IntelliJ-specific storage/UI).