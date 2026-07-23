Cursor credentials come from IntelliJ PasswordSafe storage (user pastes the session cookie in settings), not from Cursor's local SQLite state DB — so no on-disk `state.vscdb` scanning happens here.

Now I have a complete picture. Here is the inventory.

## Summary

**Important architectural note first:** this repo (`llm-subscription-usage-intellij`) does **not** parse local transcript/session/log files (no JSONL scanning, no SQLite reading, no `~/.claude/projects/*.jsonl` or Cursor `state.vscdb` parsing) the way the "ai-usage" project likely does. Instead, every provider works by calling that provider's **live web/API usage endpoint** with a stored OAuth token or session cookie, then parsing the **JSON HTTP response**. The one on-disk artifact it reads is Codex's own `~/.codex/auth.json` (OAuth token cache), and credentials for the other providers are pulled from IntelliJ's PasswordSafe (user pastes token/cookie in Settings) rather than scanned from the tool's local data directory. `AGENTS.md` and `docs/` contain no documented "supported providers" list — `docs/` is just PNG screenshots; the provider list has to be derived from `src/main/kotlin/de/moritzf/quota/*` package names.

Below is the parser inventory, one entry per provider/parser.

---

### 1. Claude (Anthropic Claude Code / claude.ai subscription usage)
- **File:** `src/main/kotlin/de/moritzf/quota/claude/ClaudeQuotaClient.kt` (+ `ClaudeQuota.kt`, `ClaudeQuotaException.kt`)
- **Data source:** Live HTTPS GET to `https://api.anthropic.com/api/oauth/usage` (JSON response), auth via bearer OAuth token + header `anthropic-beta: oauth-2025-04-20`, `User-Agent: claude-cli/2.1.87 (external, cli)` (impersonates the Claude CLI).
- **Key classes/functions:** `ClaudeQuotaClient.fetchQuota()` — issues request, handles 401/403/429 into typed `ClaudeQuotaException`. `parseQuota()` (companion) — deserializes `ClaudeUsageResponseDto` (kotlinx.serialization) covering `five_hour`, `seven_day`, `seven_day_sonnet`, `seven_day_opus`, `seven_day_oauth_apps`, `extra_usage`, and a `limits` array of model/surface-scoped windows.
- **Notable logic:** `firstRoutinesWindow()` tries multiple alternate/legacy field names (`seven_day_routines`, `seven_day_claude_routines`, `claude_routines`, `routines`, `routine`, `seven_day_cowork`, `cowork`) since the field name for "routines" usage has changed across API versions. `scopedLimitWindows()` maps the `limits[]` array into per-model/per-surface usage windows, deriving a friendly label from `scope.model.displayName` → `scope.model.id` → `scope.surface`, and infers period length (5h vs 7d) from the `group`/`kind` field. Extra-usage (pay-as-you-go credits) percent is computed manually from `used_credits/monthly_limit` if `utilization` isn't provided. OAuth token source: IntelliJ `OAuthCredentialsStore`/PasswordSafe (see `src/main/kotlin/de/moritzf/quota/idea/auth/`), not local Claude Code config files.

### 2. Cursor
- **Files:** `src/main/kotlin/de/moritzf/quota/cursor/CursorQuotaClient.kt`, `CursorQuota.kt`, `CursorSessionTokenParser.kt`, `CursorAuth.kt`; IDE-side `src/main/kotlin/de/moritzf/quota/idea/cursor/CursorCredentialsStore.kt`.
- **Data source:** Live HTTPS calls to `https://api2.cursor.sh` using a Bearer JWT extracted from the browser's `WorkosCursorSessionToken` cookie (user pastes the cookie value into Settings; stored via PasswordSafe).
- **Key classes:** `CursorSessionTokenParser` — parses the cookie format `userId::accessToken` (URL-decoded from `userId%3A%3AaccessToken`), extracting the JWT (must start with `eyJ`) and user id via `extractAccessToken()`/`extractUserId()`; also builds the `Cookie:` header for API calls. `CursorQuotaClient` — fetches plan/usage/spend-limit data into `CursorQuota` (`CursorPlanUsage`, `CursorOnDemandUsage`, `CursorRequestUsage`, `CursorSpendLimit`).
- **Notable quirk:** No parsing of Cursor's local `state.vscdb` SQLite DB (where Cursor itself stores session state) — this plugin relies entirely on the pasted session cookie.

### 3. GitHub Copilot
- **Files:** `src/main/kotlin/de/moritzf/quota/github/GitHubQuotaClient.kt`, `GitHubQuota.kt`, `GitHubOAuthClient.kt`.
- **Data source:** GitHub OAuth device-flow login, then live REST calls to GitHub's Copilot quota/usage API (JSON).
- **Key classes:** `GitHubOAuthClient` — handles device-code OAuth flow. `GitHubQuotaClient` (230 lines) — fetches and parses Copilot usage/quota JSON into `GitHubQuota`. Also used by `GitHubCopilotSubscriptionProxyProvider` (proxy mode) for live model discovery (per AGENTS.md, Copilot models come from provider's own model-list endpoint rather than a hardcoded list).

### 4. OpenAI Codex (ChatGPT/Codex subscription usage)
- **Files:** `src/main/kotlin/de/moritzf/quota/openai/OpenAiCodexQuotaClient.kt`, `OpenAiCodexQuota.kt`, `OpenAiCodexQuotaSerializer.kt`, `UsageWindow.kt`, `dto/UsageResponseDto.kt`, `dto/UsageWindowDto.kt`, `dto/RateLimitDto.kt`; auth loading in `src/main/kotlin/de/moritzf/proxy/auth/AuthLoader.kt` + `AuthFileResolver.kt`.
- **Data source:** Live HTTPS GET to `https://chatgpt.com/backend-api/wham/usage` (JSON) plus companion `rate-limit-reset-credits` endpoint; auth via Bearer token + `ChatGPT-Account-Id` header. Token itself is read from **on-disk** `~/.codex/auth.json` (`AuthFileResolver` resolves candidates, default `~/.codex/auth.json`, fallback `~/.chatgpt-local/auth.json`), the one true "local file" case in this repo.
- **Key classes:** `OpenAiCodexQuotaClient.fetchQuota()` — decodes `OpenAiCodexQuota` from JSON via kotlinx.serialization, validates `hasUsageState()`, merges in `resetCredits` from a second endpoint. `AuthLoader.loadAuthTokens()` — reads `auth.json`, extracts `tokens.access_token/id_token/refresh_token/account_id`, decides via `shouldRefreshAccessToken()` (checks JWT `exp` claim via `JwtParser`, or 55-min staleness) whether to refresh via OAuth `refresh_token` grant, then atomically rewrites `auth.json` (temp file + atomic move, POSIX chmod 600 / Windows ACL owner-only).
- **Notable quirk:** `consumeResetCredit()` supports "resetting" a rate-limit window (spends a reset credit) — a Codex-specific feature. `JwtParser` (`src/main/kotlin/de/moritzf/proxy/util/JwtParser.kt`) decodes JWT claims (base64url) to derive account id and expiry without verifying signature.

### 5. Kimi (Moonshot AI)
- **Files:** `src/main/kotlin/de/moritzf/quota/kimi/KimiQuotaClient.kt`, `KimiQuota.kt`, `KimiDeviceHeaders.kt`, `KimiWebSearchClient.kt`.
- **Data source:** Live HTTPS calls to Kimi's account/usage API, with device-fingerprint headers (`KimiDeviceHeaders`) required by Kimi's backend.
- **Key classes:** `KimiQuotaClient` (162 lines) — fetch + JSON parse into `KimiQuota`. `KimiWebSearchClient` — separate quota tracking for Kimi's web-search feature/credits.

### 6. MiniMax
- **Files:** `src/main/kotlin/de/moritzf/quota/minimax/MiniMaxQuotaClient.kt`, `MiniMaxQuota.kt`, `MiniMaxWebSearchClient.kt`.
- **Data source:** Live HTTPS JSON API calls to MiniMax account/usage endpoint.
- **Key classes:** `MiniMaxQuotaClient` (183 lines) parses quota JSON into `MiniMaxQuota`; `MiniMaxWebSearchClient` parses a separate web-search credit/usage response.

### 7. Ollama (cloud/hosted quota, not local model usage)
- **Files:** `src/main/kotlin/de/moritzf/quota/ollama/OllamaQuotaClient.kt`, `OllamaQuota.kt`, `OllamaWebSearchClient.kt`.
- **Data source:** Live JSON API (Ollama's cloud account usage/turbo quota), not local Ollama server logs.
- **Key classes:** `OllamaQuotaClient` (147 lines), `OllamaWebSearchClient`.

### 8. SuperGrok (xAI)
- **Files:** `src/main/kotlin/de/moritzf/quota/supergrok/SuperGrokQuotaClient.kt`, `SuperGrokQuota.kt`, `SuperGrokWebSearchClient.kt`, `SuperGrokImagineClient.kt`.
- **Data source:** Live JSON API calls to xAI/Grok account endpoints; per AGENTS.md, SuperGrok/xAI has a "usable official model endpoint" so live model discovery is preferred over hardcoded lists.
- **Key classes:** `SuperGrokQuotaClient` (230 lines, largest of the quota clients) — parses usage/quota JSON into `SuperGrokQuota`; `SuperGrokImagineClient` and `SuperGrokWebSearchClient` parse separate feature-specific credit/usage responses.

### 9. Z.ai (zai)
- **Files:** `src/main/kotlin/de/moritzf/quota/zai/ZaiQuotaClient.kt`, `ZaiQuota.kt`, `ZaiWebSearchClient.kt`.
- **Data source:** Live JSON API to Z.ai account/usage endpoint.
- **Key classes:** `ZaiQuotaClient` (223 lines), `ZaiWebSearchClient`.

### 10. OpenCode (opencode.ai Go/Zen subscription)
- **Files:** `src/main/kotlin/de/moritzf/quota/opencode/OpenCodeQuotaClient.kt` (396 lines, largest parser), `OpenCodeQuota.kt`, `SolidStartValueParser.kt`.
- **Data source:** Live calls to OpenCode's **SolidStart server-function RPC** (`?id=<functionId>&args=<encoded>`), authenticated via session cookie (`Cookie: auth=...`), plus custom headers `X-Server-Id`/`X-Server-Instance`/`Referer`/`Origin` mimicking the SolidStart client. Response is **not plain JSON** — it's SolidStart's own serialized-value wire format.
- **Key classes:** `OpenCodeQuotaClient` — `fetchQuota()` (per-workspace quota + billing balance), `fetchWorkspaces()` (enumerates all workspaces, tags Go/Zen eligibility), `discoverWorkspaceId()` (auto-picks first workspace with usable Go usage state or Zen credits). `SolidStartValueParser` — a **hand-rolled recursive-descent parser for SolidStart's custom serialization format**, not standard JSON: supports object/array/string/number literals, `!0`/`!1`/`true`/`false` booleans, `new Date("...")` literals, and critically `$R[n]` / `$R[n]=value` **back-reference expressions** (SolidStart's cyclic/shared-object reference syntax) resolved via an internal `references` map keyed by index.
- **Notable quirk:** This is the only non-standard-JSON wire format among all parsers in the repo — everything else is `kotlinx.serialization` JSON decoding; OpenCode required a custom parser because the SolidStart RPC response isn't valid JSON.

### 11. OpenCode Zen (proxy-only variant)
- **File:** `src/main/kotlin/de/moritzf/quota/opencode/proxy/OpenCodeZenSubscriptionProxyProvider.kt` — wraps OpenCode credentials for the local OpenAI-compatible proxy server rather than doing its own usage parsing (reuses `OpenCodeQuotaClient`).

### Shared/generic infrastructure (not a provider, but load-bearing for all parsers)
- `src/main/kotlin/de/moritzf/quota/shared/JsonSupport.kt` (referenced, not read) — presumably central `kotlinx.serialization.json.Json` config used by every quota client's `decodeFromString<T>()`.
- `src/main/kotlin/de/moritzf/quota/shared/ProviderQuota.kt` — common quota interface/shape.
- `src/main/kotlin/de/moritzf/quota/idea/common/QuotaProviderRegistry.kt` + `QuotaProviderType.kt` — registry wiring all providers into the plugin's aggregation layer.
- `src/main/kotlin/de/moritzf/quota/idea/common/QuotaUsageService.kt` / `QuotaSnapshotCache.kt` — aggregation/caching layer that polls each provider's client and caches `QuotaUsageSnapshot`.
- `src/main/kotlin/de/moritzf/proxy/util/JwtParser.kt` — generic JWT claims decoder (base64url, no signature verification) used by Codex/Claude OAuth flows to read `exp`/account-id claims.
- `src/main/kotlin/de/moritzf/proxy/auth/AuthFileResolver.kt` — resolves the Codex `auth.json` path candidates (`~/.codex/auth.json`, `~/.chatgpt-local/auth.json`, env override).
- `src/main/kotlin/de/moritzf/proxy/auth/AuthManager.kt` / `AuthLoader.kt` — default file-based OAuth credential provider for the standalone/CLI proxy mode.
- `src/main/kotlin/de/moritzf/proxy/model/CodexClientVersionResolver.kt` — not a usage parser but resolves/spoofs Codex CLI client version strings for API compatibility.

### Not present in this repo
No parsers for local Claude Code session transcripts (`~/.claude/projects/**/*.jsonl`), no Cursor local SQLite `state.vscdb`/`state.vscdb.backup` reading, no Codex local session `.jsonl` rollout files, no cost-per-token calculation from local logs, and no generic "model pricing table" for computing USD cost from token counts — everything is provider-reported usage/quota percentages from each vendor's own web API. This is a meaningful contrast with what "ai-usage" (which the user is building) likely needs to do, i.e., parse local on-disk transcripts/session logs directly rather than call live subscription-usage endpoints.