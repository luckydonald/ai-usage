In repo /home/user/git/luckydonald/ai-usage, find which AI-usage providers currently exist (fully implemented, with both login method and usage-fetch method) vs which are missing entirely.

Specifically check whether these providers (from two reference inventories of similar IntelliJ plugins) exist in ai-usage, and for each existing one what's implemented (login + usage) vs stub/missing:
- Claude (Anthropic) — Claude Code style OAuth usage endpoint (https://api.anthropic.com/api/oauth/usage) or ~/.claude credentials reading
- Codex/ChatGPT (OpenAI) — ~/.codex/auth.json reading, https://chatgpt.com/backend-api/wham/usage
- Cursor — WorkosCursorSessionToken cookie, cursor.com/api/usage-summary
- GitHub Copilot — device flow OAuth, api.github.com/copilot_internal/user
- Kimi (Moonshot)
- MiniMax
- Ollama (cloud/turbo quota)
- SuperGrok (xAI)
- Z.ai
- OpenCode (Zen)
- Cline
- Nebius
- OpenRouter
- OpenAI Platform (admin API usage)
- Xiaomi

Also check: does ai-usage instead read LOCAL transcript/session logs (JSONL, SQLite) for token counting rather than calling live vendor usage APIs? Compare architecture style.

List findings as a table: provider name | exists in ai-usage (yes/no/partial) | file paths if exists | what's missing if partial. Also note the general architectural difference (local log parsing vs live API polling) if any.

Return concise findings with file:line references.