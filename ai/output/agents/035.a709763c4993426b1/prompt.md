Repo at ~/git/moritzfl/llm-subscription-usage-intellij (Kotlin IntelliJ plugin project, build.gradle.kts, src/, docs/, AGENTS.md).

Task: find all code that parses AI agent usage data — usage logs, token counts, session/transcript files, cost data, subscription usage, for tools like Claude Code, Copilot, Codex, Cursor, etc. This project ("ai-usage") tracks similar things, so we want an inventory of every parser implementation in that repo.

For each parser found, report:
- File path (full path)
- Which AI tool/provider it parses (Claude, Copilot, Codex, Cursor, JetBrains AI, etc.)
- What data source format it reads (JSONL files, SQLite DB, log files, API responses, config files) and roughly where those live on disk
- Key classes/functions and their responsibility (parsing, aggregation, model detection, cost calculation)
- Any notable parsing logic/quirks (regex patterns, edge cases handled, file locations searched)

Also check AGENTS.md and docs/ for any documented list of supported providers/parsers.

Be thorough — search src/ directory structure for keywords like "parser", "usage", "provider", "reader", "scanner", "collector". List every distinct parser class you find, don't just summarize a few examples. Report back in a structured list, one entry per parser/provider.