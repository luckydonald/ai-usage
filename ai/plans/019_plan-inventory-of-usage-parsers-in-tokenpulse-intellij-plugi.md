# Plan: Inventory of usage parsers in tokenpulse-intellij-plugin

## Context
User wants inventory of how `~/git/DimazzzZ/tokenpulse-intellij-plugin` reads AI-agent usage data, so components can serve as reference/comparison for `ai-usage` project's own provider parsers.

## Key finding
Plugin has **no local jsonl/sqlite log parsers** (no Claude Code `~/.claude/projects/*.jsonl`, no Cursor sqlite, no Aider history, no Copilot logs). Every provider: read local OAuth/API credential (JSON file or macOS Keychain) → call vendor's remote HTTPS usage/billing API → parse JSON response. Credential reading is local-file/keychain; usage numbers always come from network.

Source tree: `src/main/kotlin/org/zhavoronkov/tokenpulse/provider/<vendor>/`

## Plan items (one per parser/component)

1. **Claude Code** — `provider/anthropic/claudecode/`
   - `ClaudeConfigLocator.kt` — path resolver: `~/.claude`, `.credentials.json`, `~/.claude.json`, Keychain service name
   - `ClaudeCredentialReader.kt` — reads Keychain or `~/.claude/.credentials.json` (`claudeAiOauth.{accessToken,refreshToken,expiresAt,scopes}`), writes rotated tokens back
   - `ClaudeAccountIdentityReader.kt` — reads `~/.claude.json` for linked account email/org
   - `ClaudeAccountDiscovery.kt` — scans disk/env (`CLAUDE_CONFIG_DIR`) for multiple accounts
   - `ClaudeCliDetector.kt` — detects `claude` CLI on PATH
   - `ClaudeOAuthRefreshClient.kt` — POST Anthropic OAuth token endpoint
   - `ClaudeOAuthUsageClient.kt` — **GET `https://api.anthropic.com/api/oauth/usage`**, parses `ClaudeUsageData` (tokens/cost/limits)
   - `ClaudeUsageData.kt`, `ClaudeOAuthResponse.kt` — data classes
   - `ClaudeCodeProviderClient.kt` — orchestrator

2. **Codex / ChatGPT** — `provider/openai/chatgpt/`
   - `CodexConfigLocator.kt` — resolves `~/.codex`, `auth.json`
   - `CodexAuthDotJson.kt` — model for `~/.codex/auth.json`
   - `CodexCredentialReader.kt` — reads local `auth.json` (accessToken/refreshToken/account id)
   - `CodexOAuthRefreshClient.kt` — OAuth refresh POST
   - `CodexOAuthUsageClient.kt` — **GET `https://chatgpt.com/backend-api/wham/usage`** (FedRAMP variant supported)
   - `CodexCliExecutor.kt` — detects/runs local `codex` CLI
   - `CodexProviderClient.kt` — orchestrator

3. **Cline** — `provider/cline/ClineProviderClient.kt`
   - stored API secret → **`https://api.cline.bot/api/v1/users/{me,balance,usages,plan/usage-limits}`**, parses `BalanceResponse`/`UsagesResponse`

4. **Nebius** — `provider/nebius/NebiusProviderClient.kt`
   - API key → `https://tokenfactory.nebius.com` billing/usage endpoints

5. **OpenRouter** — `provider/openrouter/`
   - `OpenRouterProviderClient.kt` — `https://openrouter.ai` credits/usage API
   - `OpenRouterPluginBridgeClient.kt` — inter-plugin bridge (reads from another installed plugin, not disk)

6. **OpenAI Platform** — `provider/openai/platform/OpenAiPlatformProviderClient.kt`
   - Admin API key → `https://api.openai.com` org usage endpoints (paginated `pageCursor`), own OAuth token endpoint

7. **Xiaomi** — `provider/xiaomi/`
   - `XiaomiProviderClient.kt` — `https://platform.xiaomimimo.com` usage/billing
   - `XiaomiSessionRefresher.kt` — `https://account.xiaomi.com` session refresh
   - `XiaomiResponseParser.kt` — parses JSON API responses into usage/session models

8. **Shared infra** (reused across all providers)
   - `provider/SessionParser.kt` — generic Gson JSON-secret parser + validator callback
   - `provider/oauth/OAuthCredentialStore.kt` — local credential persistence (atomic writes)
   - `provider/oauth/{AbstractOAuthUsageClient,AbstractOAuthRefreshClient,TokenExpiry,OAuthHttp}.kt` — shared bearer-token HTTP client base classes
   - `provider/{ProviderRegistry,ProviderClient}.kt` — registry/interface tying providers into UI

## Not present
No Cursor, GitHub Copilot, Gemini CLI, or Aider integration (no matches for names, no jsonl/sqlite parsing anywhere in `src/main`).

## Verification
This is a research/inventory task — no code changes made. Verify by spot-checking a couple of the listed files directly in `~/git/DimazzzZ/tokenpulse-intellij-plugin/src/main/kotlin/org/zhavoronkov/tokenpulse/provider/` against the descriptions above.
