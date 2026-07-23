# Plan: Inventory parsers in llm-subscription-usage-intellij

## Context
User want inventory of AI-agent-usage parsers in `~/git/moritzfl/llm-subscription-usage-intellij`, as plan items — likely reference for possible reuse/comparison with this project (`ai-usage`).

Key finding: architecture differs fundamentally from `ai-usage`. That repo does NOT parse local transcript/session files (no JSONL, no SQLite). Every provider calls a **live web/API usage endpoint** with stored OAuth token or session cookie, then parses JSON (except OpenCode, custom SolidStart format). Only one local file read: Codex's `~/.codex/auth.json` (token cache, not usage data).

No code changes needed — this is inventory/knowledge gathering only.

## Plan items (parser inventory)

1. **Claude** — `src/main/kotlin/de/moritzf/quota/claude/ClaudeQuotaClient.kt` (+`ClaudeQuota.kt`). Live GET `api.anthropic.com/api/oauth/usage`, kotlinx.serialization JSON. Handles legacy field-name fallbacks for "routines" usage, per-model/per-surface limit windows.

2. **Cursor** — `src/main/kotlin/de/moritzf/quota/cursor/{CursorQuotaClient,CursorQuota,CursorSessionTokenParser,CursorAuth}.kt`. Live calls to `api2.cursor.sh`, JWT extracted from pasted `WorkosCursorSessionToken` cookie. No local `state.vscdb` read.

3. **GitHub Copilot** — `src/main/kotlin/de/moritzf/quota/github/{GitHubQuotaClient,GitHubQuota,GitHubOAuthClient}.kt`. OAuth device flow, live REST usage/quota JSON.

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
