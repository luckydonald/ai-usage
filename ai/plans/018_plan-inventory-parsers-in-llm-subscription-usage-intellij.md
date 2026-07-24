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

4. **OpenAI Codex** — `src/main/kotlin/de/moritzf/quota/openai/*` + `src/main/kotlin/de/moritzf/proxy/auth/{AuthLoader,AuthFileResolver}.kt`. Live GET `chatgpt.com/backend-api/wham/usage`; token read from on-disk `~/.codex/auth.json` (only local-file case), auto-refresh via JWT `exp` check.

5. **Kimi (Moonshot)** — `src/main/kotlin/de/moritzf/quota/kimi/{KimiQuotaClient,KimiQuota,KimiDeviceHeaders,KimiWebSearchClient}.kt`. Live API with device-fingerprint headers.

6. **MiniMax** — `src/main/kotlin/de/moritzf/quota/minimax/{MiniMaxQuotaClient,MiniMaxQuota,MiniMaxWebSearchClient}.kt`. Live JSON API.

7. **Ollama (cloud/turbo quota)** — `src/main/kotlin/de/moritzf/quota/ollama/{OllamaQuotaClient,OllamaQuota,OllamaWebSearchClient}.kt`. Live cloud-account API, not local Ollama server logs.

8. **SuperGrok (xAI)** — `src/main/kotlin/de/moritzf/quota/supergrok/*`. Live JSON API, largest single client (230 lines).

9. **Z.ai** — `src/main/kotlin/de/moritzf/quota/zai/{ZaiQuotaClient,ZaiQuota,ZaiWebSearchClient}.kt`. Live JSON API.

10. **OpenCode (Go/Zen)** — `src/main/kotlin/de/moritzf/quota/opencode/{OpenCodeQuotaClient,OpenCodeQuota,SolidStartValueParser}.kt` (396 lines, largest parser overall). Custom hand-rolled recursive-descent parser for SolidStart RPC wire format (non-JSON: `!0`/`!1` booleans, `new Date(...)`, `$R[n]` back-references). Only non-JSON wire format in repo.

11. **OpenCode Zen proxy variant** — `src/main/kotlin/de/moritzf/quota/opencode/proxy/OpenCodeZenSubscriptionProxyProvider.kt`. Wraps OpenCode credentials for local proxy, reuses `OpenCodeQuotaClient`.

12. **Shared infra** (not providers, but load-bearing): `quota/shared/{JsonSupport,ProviderQuota}.kt`, `quota/idea/common/{QuotaProviderRegistry,QuotaProviderType,QuotaUsageService,QuotaSnapshotCache}.kt`, `proxy/util/JwtParser.kt` (generic JWT claim decode, no sig verify), `proxy/auth/AuthManager.kt`.

## Not present in that repo
No local transcript/session-log parsing (`~/.claude/projects/**/*.jsonl`, Cursor SQLite, Codex rollout files), no token-cost calculation, no pricing tables. Everything is vendor-reported usage percentages via live API — contrasts with `ai-usage`'s likely local-log-parsing approach.

## Verification
None needed — read-only inventory task, no code written.
