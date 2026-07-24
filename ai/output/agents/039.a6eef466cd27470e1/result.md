Have enough. Writing final markdown report.

## OpenAI Codex

**Credential source:** File read, not user-pasted. `AuthLoader.loadAuthTokens()` (`src/main/kotlin/de/moritzf/proxy/auth/AuthLoader.kt`) resolves candidate paths via `AuthFileResolver.resolveCandidates()`: env `CHATGPT_LOCAL_HOME`/`auth.json`, env `CODEX_HOME`/`auth.json`, `~/.chatgpt-local/auth.json`, `~/.codex/auth.json` (first existing file wins). Expected JSON shape: top-level object with `tokens: {access_token, id_token, refresh_token, account_id}` and `last_refresh` (ISO instant string). If `account_id` absent, derived from `id_token` JWT claim `https://api.openai.com/auth.chatgpt_account_id` via `JwtParser.deriveAccountId()`. User must have already run `codex login` externally to create this file — plugin never prompts for token input, only reads what Codex CLI wrote.

**Token refresh:** `shouldRefreshAccessToken()` triggers refresh if access-token JWT `exp` claim is within 5 min (`REFRESH_EXPIRY_MARGIN_MS`) of expiring, or if `last_refresh` is older than 55 min (`REFRESH_INTERVAL_MS`), or if access token missing. Refresh: POST to `{issuer}/oauth/token` (issuer default `ServerConfig.DEFAULT_ISSUER`, overridable via `CHATGPT_LOCAL_ISSUER` env or param) with JSON body `{grant_type: "refresh_token", refresh_token, client_id, scope: "openid profile email offline_access"}`. `client_id` defaults to `ServerConfig.DEFAULT_CLIENT_ID` or env `CHATGPT_LOCAL_CLIENT_ID`. On success, rewrites `auth.json` atomically (temp file, `chmod 600`/Windows ACL owner-only, then `ATOMIC_MOVE`).

**API calls:**
- `GET https://chatgpt.com/backend-api/wham/usage` — headers: `Authorization: Bearer {accessToken}`, `Accept: application/json`, optional `ChatGPT-Account-Id: {accountId}`.
- `GET https://chatgpt.com/backend-api/wham/rate-limit-reset-credits` — same auth headers.
- `POST https://chatgpt.com/backend-api/wham/rate-limit-reset-credits/consume` — same auth headers + `Content-Type: application/json`; body `{credit_id, redeem_request_id: <random UUID>}`.

**Data models** (`openai/dto/*.kt`, kotlinx.serialization):
- `UsageResponseDto`: `user_id`, `account_id`, `email`, `rate_limit: RateLimitDto?`, `code_review_rate_limit: RateLimitDto?`, `plan_type`, `credits: CreditsDto?`, `spend_control: SpendControlDto?`, `rate_limit_reached_type: RateLimitReachedTypeDto?`, `rate_limit_reset_credits: RateLimitResetCredits?`, `additional_rate_limits: List<AdditionalRateLimitDto>?`.
- `RateLimitDto`: `allowed: Boolean?`, `limit_reached: Boolean?`, `primary_window: UsageWindowDto?`, `secondary_window: UsageWindowDto?`.
- `UsageWindowDto`: `used_percent: Double?`, `limit_window_seconds: Double?`, `reset_at: Double?` (epoch seconds, converted to ms).
- `CreditsDto`: `has_credits`, `unlimited`, `overage_limit_reached`, `balance: String?`, `approx_local_messages: List<Int>?`, `approx_cloud_messages: List<Int>?`.
- `SpendControlDto`: `reached: Boolean?`, `individual_limit: Double?`.
- `RateLimitReachedTypeDto`: `type`, `details`.
- `AdditionalRateLimitDto`: `limit_name`, `metered_feature`, `rate_limit: RateLimitDto?` — used for arbitrary extra metered features beyond primary/secondary/review windows.
- Domain object `OpenAiCodexQuota`: `primary/secondary/reviewPrimary/reviewSecondary: UsageWindow?`, `planType`, `allowed`, `limitReached`, `reviewAllowed`, `reviewLimitReached`, `accountId`, `email`, `credits`, `spendControl`, `rateLimitReachedType`, `resetCreditsAvailableCount: Int`, `resetCredits: List<RateLimitResetCredit>`, `extraRateLimits: List<OpenAiExtraRateLimit>`, `fetchedAt`, `rawJson`.

**Quirks:** `AdditionalRateLimitDto.displayTitle()` strips `gpt-<version>-` prefixes and title-cases feature names via regex; window naming buckets duration into "5-hour"/"Weekly"/"Monthly"/etc. by comparing seconds with 60s tolerance. `toString()` redacts `rawJson`/`accountId`/`email`. Reset-credits endpoint failures are swallowed (`runCatching { }.getOrDefault(...)`) rather than thrown — so this call fails silently and quota data still returns.

## Kimi

**Credential source:** Fully automated OAuth 2.0 Device Authorization Grant — no manual paste. `KimiOAuthClient.requestDeviceAuthorization()` → `POST https://auth.kimi.com/api/oauth/device_authorization` (form-encoded `client_id=17e5f671-d194-4dfb-9706-5516cb48c098`) returns `user_code`, `device_code`, `verification_uri(_complete)`, `expires_in`, `interval`. User opens the verification URL in browser and approves; plugin polls `POST https://auth.kimi.com/api/oauth/token` (form: `client_id`, `device_code`, `grant_type=urn:ietf:params:oauth:grant-type:device_code`) until `access_token` returned (handles `authorization_pending`/`slow_down`/`expired_token` errors). Resulting `KimiCredentials` (`accessToken`, `refreshToken`, `expiresAtEpochSeconds`, `scope`, `tokenType`) is serialized to JSON and stored via IntelliJ `PasswordSafe` under `CredentialAttributes("Kimi Credentials", "kimi-credentials")`.

**Device fingerprint:** every OAuth request (`KimiOAuthClient.postForm`) also sends `KimiDeviceHeaders.all()`: `X-Msh-Platform: kimi_cli`, `X-Msh-Version: 1.40.0`, `X-Msh-Device-Name` (local hostname), `X-Msh-Device-Model` (OS+version+arch string, e.g. `sw_vers -productVersion` on macOS), `X-Msh-Os-Version`, `X-Msh-Device-Id` (random UUID persisted in IntelliJ `PropertiesComponent` under key `kimi.oauth.device.id`).

**Token refresh:** `KimiCredentialRefresher.refreshIfNeeded()`/`refresh()` (in `KimiQuotaClient.fetchQuota`) — proactively refreshes before request if needed, and reactively re-fetches once on HTTP 401/403 via `refresh()`, throwing `KimiQuotaException("Session expired...")` if that also fails. (Refresh token endpoint itself is `TOKEN_ENDPOINT = https://auth.kimi.com/api/oauth/token`, same as device-flow polling endpoint, presumably `grant_type=refresh_token` — refresher class not read in full here but wired into client via constructor.)

**API call:** `GET https://api.kimi.com/coding/v1/usages` — headers: `Authorization: Bearer {accessToken}`, `Accept: application/json`.

**Data models:**
- `KimiUsageResponseDto`: `usage: KimiLimitDetailDto?` (aggregate/total), `limits: List<KimiLimitDto>` (per-window entries), `user: KimiUserDto?`.
- `KimiLimitDto`: `window: KimiWindowDto?`, `detail: KimiLimitDetailDto?`.
- `KimiWindowDto`: `duration: Long?`, `timeUnit: String?` (`TIME_UNIT_MINUTE`/`_HOUR`/`_DAY`).
- `KimiLimitDetailDto`: `limit: String?`, `remaining: String?`, `resetTime: String?` (ISO instant; note `limit`/`remaining` are strings, parsed via `toLongOrNull()`).
- `KimiUserDto.membership: KimiMembershipDto?` → `level: String?` (`LEVEL_INTERMEDIATE`/`LEVEL_ADVANCED`/`LEVEL_PREMIUM`).
- Domain `KimiQuota`: `plan: String`, `sessionUsage: KimiUsageWindow?`, `totalUsage: KimiUsageWindow?`, `fetchedAt`, `rawJson`.
- `KimiUsageWindow`: `used: Long`, `limit: Long`, `usagePercent: Double`, `resetsAt: Instant?`, `periodDurationMs: Long?`.

**Quirks:** session window is selected as the limit whose `window.duration == 300 && timeUnit == "TIME_UNIT_MINUTE"` (5-minute window), falling back to `limits.firstOrNull()`. `used` computed as `limit - remaining` clamped to ≥0 since API doesn't always send a direct "used" count for the per-window detail. Membership level string normalized into a display plan name (e.g. `LEVEL_ADVANCED` → "Kimi Code Advanced"), with generic fallback formatting for unrecognized levels.

## MiniMax

**Credential source:** Direct user input — raw API key pasted into a `JBPasswordField` in `MiniMaxSettingsPanel` (labelled "API key:"), saved via `MiniMaxApiKeyStore.save()` into IntelliJ `PasswordSafe` under `CredentialAttributes("MiniMax API Key", "minimax-api-key")` as a plain string (not JSON-wrapped, unlike Kimi's credential blob). No OAuth, no file read — pure static bearer key the user must obtain from MiniMax's own dashboard and paste manually. Settings panel also lets user pick a `MiniMaxRegionPreference` (Global vs CN) via combo box, persisted in `QuotaSettingsState`.

**Token refresh:** None — static API key, no expiry/refresh logic.

**API calls:** `GET` against a region-dependent list of fallback endpoints, tried in order until one succeeds (stops immediately on 401/403 without trying further fallbacks):
- Global region: `https://api.minimax.io/v1/api/openplatform/coding_plan/remains`, then `https://api.minimax.io/v1/coding_plan/remains`, then `https://www.minimax.io/v1/api/openplatform/coding_plan/remains`.
- CN region: `https://api.minimaxi.com/v1/api/openplatform/coding_plan/remains`, then `https://api.minimaxi.com/v1/coding_plan/remains`.
Headers on every attempt: `Authorization: Bearer {apiKey}`, `Content-Type: application/json`, `Accept: application/json`.

**Data models:**
- `MiniMaxResponseDto`: `base_resp: MiniMaxBaseRespDto?`, `model_remains: List<MiniMaxRemainDto>`.
- `MiniMaxBaseRespDto`: `status_code: Int?` (0 = success), `status_msg: String?`.
- `MiniMaxRemainDto`: `current_interval_total_count: Long?`, `current_interval_usage_count: Long?`, `current_interval_used_count: Long?`, `current_interval_remaining_count: Long?`, `current_interval_remains_count: Long?`, `start_time: Long?`, `end_time: Long?`, `remains_time: Long?` (seconds remaining, relative), `current_subscribe_title: String?`, `plan_name: String?`, `plan: String?`.
- Domain `MiniMaxQuota`: `plan: String`, `region: MiniMaxRegion`, `sessionUsage: MiniMaxUsageWindow`, `fetchedAt`, `rawJson`.

**Quirks:** three different candidate field names used across API versions for remaining/used counts (`current_interval_usage_count` vs `_remaining_count` vs `_remains_count`), tried in that priority order; `used` derived as `total - remaining` if no explicit used-count field present. `epochSecondsOrMillis()` heuristically distinguishes seconds-since-epoch vs millis-since-epoch by checking if value < 10 billion. Plan name inferred from numeric quota limit via hardcoded per-region tables (e.g. Global 1000/15000 → "MiniMax Coding Max") when API doesn't return a plan name string directly. Region suffix like " (GLOBAL)" appended to plan display name unless already present.