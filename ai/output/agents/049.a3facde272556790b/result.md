Confirmed exactly per the specific reference endpoints named in the task (chatgpt.com backend-api, `~/.codex/auth.json`). I have enough to report.

## Findings

**Architecture:** `ai-usage` is a **live vendor-API polling tool**, not a local-transcript-mining tool. Its own SQLite (`src/ai_usage/database.py`) and JSONL files (`src/ai_usage/history.py`, `src/ai_usage/notes.py`) are just its *own* result-cache/history store — they record snapshots of what it fetched, not vendor session transcripts. Usage numbers come from either:
- vendor **private web APIs** via `curl_cffi.requests.AsyncSession` with captured cookies (`base_url="https://claude.ai"` in `providers/claude/usage/web/private_api.py:186`; `base_url="https://chatgpt.com"` in `providers/codex/usage/web/private_api.py:202`; `https://api.github.com` in `providers/copilot/usage/web/{billing_api,quota_api}.py`), or
- shelling out to the **local CLI binary** (`claude`, `codex`) and parsing its output/relay file (`providers/claude/usage/cli/*`, `providers/codex/usage/cli/*`).

It does read a local credential file (`~/.codex/auth.json` — `providers/codex/login/local/auth_json.py:25`; Claude's local settings file — `providers/claude/login/local/settings_file.py`), but only to obtain/reuse a token, never to parse token-usage transcripts.

Provider registry (`src/ai_usage/providers/registry.py:56-67`) confirms only three services are wired in: `claude`, `codex`, `copilot`. No entry-point plugins are shipped in this repo either.

| Provider | Exists | Login | Usage | File paths |
|---|---|---|---|---|
| Claude (Anthropic) | Yes, full | `SettingsFileLogin` (local), `CookieCaptureLogin` (web) | `PrivateApiUsage` (claude.ai private API), `RelayFileUsage`/`DirectCliUsage`/`InteractiveCliUsage` (CLI) | `src/ai_usage/providers/claude/provider.py`, `.../login/local/settings_file.py`, `.../login/web/cookie_capture.py`, `.../usage/web/private_api.py`, `.../usage/cli/{direct,interactive}.py`, `.../usage/local/relay_file.py` |
| Codex/ChatGPT (OpenAI) | Yes, full | `AuthJsonLogin` (`~/.codex/auth.json`, `login/local/auth_json.py:25`), `CookieCaptureLogin` (web) | `PrivateApiUsage` (chatgpt.com backend-api, `usage/web/private_api.py:202`), `AppServerUsage`, `StatusPtyUsage` (CLI) | `src/ai_usage/providers/codex/provider.py`, `.../login/local/auth_json.py`, `.../login/web/cookie_capture.py`, `.../usage/web/private_api.py`, `.../usage/cli/{app_server,status_ptv}.py` |
| GitHub Copilot | Yes, full | `TokenReuseLogin` (local CLI token reuse); billing provider has no login (external credential) | `BillingApiUsage`, `QuotaApiUsage` (api.github.com), `GenericPrivateWebUsage` (experimental) | `src/ai_usage/providers/copilot/provider.py`, `.../login/cli/token_reuse.py`, `.../usage/web/{billing_api,quota_api,entitlements}.py` |
| Cursor | No | — | — | not present |
| Kimi (Moonshot) | No | — | — | not present |
| MiniMax | No | — | — | not present |
| Ollama | No | — | — | not present |
| SuperGrok (xAI) | No | — | — | not present |
| Z.ai | No | — | — | not present |
| OpenCode (Zen) | No | — | — | not present |
| Cline | No | — | — | not present |
| Nebius | No | — | — | not present |
| OpenRouter | No | — | — | not present |
| OpenAI Platform (admin API) | No | — | — | not present |
| Xiaomi | No | — | — | not present |

Bottom line: of the 15 providers checked, only Claude, Codex, and Copilot exist, and all three are fully wired (login method + usage method, registered in `registry.py`). The other 12 are entirely absent — no stub files, no partial classes, nothing under `providers/`. The extensibility mechanism (`ProviderRegistry.load_entry_points`, `registry.py:44-50`) would let an external package add them via `ai_usage.providers` entry points, but none ship in this repo.