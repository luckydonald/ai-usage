## Findings: TokenPulse plugin source (for porting to Python)

Repo: `~/git/DimazzzZ/tokenpulse-intellij-plugin`. No xAI/SuperGrok provider directory exists — `provider/` only contains `anthropic`, `cline`, `nebius`, `oauth`, `openai`, `openrouter`, `xiaomi`. Confirmed explicitly: nothing xAI/Grok-related in this repo.

### 1. Cline (`provider/cline/ClineProviderClient.kt`)

Base URL: `https://api.cline.bot`

Endpoints actually called by `fetchBalance`/`testCredentials` (current, live code path):
- `GET {base}/api/v1/users/me` — identity
- `GET {base}/api/v1/users/{userId}/balance` — balance (userId from previous call)
- `GET {base}/api/v1/users/{userId}/usages` — usage transactions
- `GET {base}/api/v1/users/me/plan/usage-limits` — best-effort ClinePass windows

Endpoints only *documented in KDoc comments but NOT called by any code in this class* (org billing is explicitly bypassed for API-key auth per code comment "Organization billing is managed separately and doesn't use API keys"): `GET /api/v1/organizations/{id}/balance`, `GET /api/v1/organizations/{id}/members/{memberId}/usages`. Test file still POSTs `organizations` array in the `/me` mock JSON, but the current `UserResponse` data class only declares `val id: String` — the `organizations` field is ignored by Gson (extra field), dead weight.

Auth header: `Authorization: Bearer $secret` (raw API key, no other custom headers) on every request.

Response envelope (all endpoints): `{"success": bool, "data": {...}}`. Parsing rule: only treat as valid if `success == true`; then `gson.fromJson(data, T::class.java)`. `success:false` or missing/malformed `data` → treated as null/failure, silently (for balance/usages this means fields default to zero/empty; for plan-usage-limits it means empty metadata map).

Exact field names:
- `/users/me` → `data.id` (String) — this is the ONLY field parsed for identity. **No email field exists anywhere in the Cline response parsing** — `UserResponse` is `data class UserResponse(val id: String)`. There is no identity/email derivation for Cline at all in this plugin.
- `/users/{id}/balance` → `data.balance` (BigDecimal, in micro-dollars: 1 unit = $0.000001). Conversion: `credits.divide(BigDecimal(1_000_000), 2, RoundingMode.HALF_UP)`.
- `/users/{id}/usages` → `data.items: [{ "creditsUsed": BigDecimal, "totalTokens": Long }]`. Client sums `creditsUsed` (converted same way) and `totalTokens` across all items.
- `/users/me/plan/usage-limits` → `data.limits: [{ "type": String, "percentUsed": Int, "resetsAt": String? }]`. Recognized `type` values (literal strings): `"five_hour"`, `"weekly"`, `"monthly"`. Unknown types silently dropped. `percentUsed` clamped to `0..100`. Output metadata map keys (literal): `clinePassFiveHourUsed`, `clinePassFiveHourResetsAt`, `clinePassWeeklyUsed`, `clinePassWeeklyResetsAt`, `clinePassMonthlyUsed`, `clinePassMonthlyResetsAt`. `resetsAt` omitted from map if blank/empty/null.

HTTP status handling on `/users/me` (auth-gating call): 401/403 → AuthError; 429 → RateLimited; ≥500 → NetworkError (server error, not auth); other non-2xx → NetworkError. Balance/usages/plan-limits calls: any non-2xx is swallowed (returns null/default), never surfaces as a hard failure — `fetchBalance` still returns `Success` with zeroed values.

### 2. OpenRouter

`OpenRouterProviderClient.kt` — base URL `https://openrouter.ai`. Uses `/api/v1/credits` (NOT `/api/v1/key`).

- `GET {base}/api/v1/credits` → body `{"data": {"total_credits": <number>, "total_usage": <number, optional>}}`. Exact Gson field mapping via `@SerializedName`:
  - `@SerializedName("total_credits") val totalCredits: BigDecimal`
  - `@SerializedName("total_usage") val totalUsage: BigDecimal? = null`
  - Computed: `used = totalUsage ?: BigDecimal.ZERO`; `remaining = totalCredits.subtract(used)`; `Credits(total = totalCredits, used = used, remaining = remaining)`.
- `GET {base}/api/v1/activity` → body `{"data": [{"prompt_tokens": Long, "completion_tokens": Long}, ...]}`. Fields: `@SerializedName("prompt_tokens")`, `@SerializedName("completion_tokens")`. `Tokens.used = sum(prompt_tokens + completion_tokens)` across all entries. This call is best-effort — any failure/exception → `tokens = null`, doesn't break the balance result.
- Auth header: `Authorization: Bearer $secret` (only a **Provisioning Key** works, not a regular API key — comment/KDoc explicit: "Only Provisioning Keys are supported. Regular API keys do not expose the `/api/v1/credits` endpoint").
- Error mapping: HTTP 401 → `AuthException` → `AuthError`; HTTP 429 → `RateLimitException` → `RateLimited`; any other non-2xx (including 403, 500) → generic `ServerException` → `UnknownError` (note: 403 is NOT treated as auth here, unlike Cline — it falls into the generic "else" branch alongside 500). `JsonSyntaxException` (malformed JSON body) → `ParseError`. Generic `Exception` → `NetworkError`.

`OpenRouterPluginBridgeClient.kt` — not an HTTP client itself; uses Java reflection to pull credentials out of a co-installed IntelliJ "OpenRouter" plugin (class `org.zhavoronkov.openrouter.services.OpenRouterSettingsService`, singleton via `getInstance()`, methods `getProvisioningKey()` / `getApiKey()` via reflection). If that plugin is installed and has a provisioning key, it delegates to `OpenRouterProviderClient.fetchBalance` with that key, then tags the resulting `BalanceSnapshot.metadata` with `"source" to "openrouter-plugin"`. No new endpoints/fields — irrelevant to a standalone Python port except as a "check for sibling plugin" pattern, not applicable outside IntelliJ.

### 3. xAI / SuperGrok

No such provider exists in this repo. `provider/` top-level dirs are only: `anthropic`, `cline`, `nebius`, `oauth`, `openai`, `openrouter`, `xiaomi`. No hints to extract.

(Bonus, since it was adjacent code I had to read to check identity patterns: Anthropic's Claude Code OAuth path DOES have an explicit identity/email field — `ClaudeAccountIdentityReader.kt` line 14: `val emailAddress: String?`, parsed at line 49 from `oauth.get("emailAddress")`. Codex/OpenAI equivalent (`CodexAuthDotJson.kt`/`CodexOAuthUsageClient.kt`) uses literal field name `"email"` (`@SerializedName("email") val email: String?`), with usage-payload email taking priority over the account JWT's email as fallback. Cline has no analog to either.)

### 4. Shared OAuth/session infra (for pattern reference only, not reuse)

`provider/SessionParser.kt`:
```kotlin
object SessionParser {
    fun <T> parse(secret: String, sessionClass: Class<T>, validator: (T) -> Boolean, providerName: String, gson: Gson = Gson()): T?
}
```
Parses a JSON "secret" string (stored credential blob) into a typed session, validates via a passed predicate, returns null (logged at debug) on any parse exception or validator failure. Not used by Cline/OpenRouter (both use plain bearer tokens) — this is for OAuth-session-based providers (Claude/Codex/Xiaomi style).

`provider/oauth/AbstractOAuthUsageClient.kt`:
```kotlin
abstract class AbstractOAuthUsageClient<R>(connectSeconds: Long, private val logTag: String) {
    protected val httpClient = oauthHttpClient(connectSeconds)
    protected fun execute(request: HttpRequest): R   // send -> mapStatus(status, body); catches HttpTimeoutException/ConnectException/Exception -> transient(msg)
    protected abstract fun mapStatus(status: Int, body: String): R
    protected abstract fun transient(message: String): R
}
```

`provider/oauth/AbstractOAuthRefreshClient.kt`:
```kotlin
abstract class AbstractOAuthRefreshClient<R>(connectSeconds: Long, private val logTag: String) {
    protected val httpClient = oauthHttpClient(connectSeconds)
    fun refresh(refreshToken: String): R   // blank-token guard -> emptyTokenResult(); else send buildRequest(refreshToken) -> mapStatus
    protected abstract fun buildRequest(refreshToken: String): HttpRequest
    protected abstract fun mapStatus(status: Int, body: String): R
    protected abstract fun emptyTokenResult(): R
    protected abstract fun transient(message: String): R
    protected fun clientId(env: String, default: String): String  // System.getenv(env)?.takeIf{isNotBlank} ?: default
}
```

`provider/oauth/TokenExpiry.kt`:
```kotlin
internal fun isTokenExpired(expiry: Long?, now: Long, skew: Long): Boolean {
    if (expiry == null) return false  // can't prove expired -> treat as usable, let 401 be authoritative
    return now >= expiry - skew
}
```
Note: all three time args must share units (millis for Claude, seconds for Codex) — caller's responsibility.

`provider/oauth/OAuthHttp.kt`:
```kotlin
internal val OAUTH_USER_AGENT: String by lazy { "TokenPulse/${PluginVersion.value}" }  // e.g. "TokenPulse/0.3.1"
internal const val OAUTH_BODY_PREVIEW = 200  // max chars of body echoed into error/log messages
internal fun oauthHttpClient(connectSeconds: Long): HttpClient =
    HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(connectSeconds)).build()
```

Python-porting takeaway pattern: separate "build request" (provider-specific URL/headers/body) from "send + status-dispatch + timeout/connect-error/generic-error" (shared skeleton) — cleanly maps to a base class with `build_request()`/`map_status()` abstract methods and a shared `execute()`/`refresh()` template method, plus a pure `is_token_expired(expiry, now, skew)` helper function (same-units caveat) and a bounded body-preview constant for error messages.