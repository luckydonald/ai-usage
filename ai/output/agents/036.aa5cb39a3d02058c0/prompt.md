Repo: ~/git/DimazzzZ/tokenpulse-intellij-plugin (IntelliJ plugin, Kotlin/Java, Gradle).

Goal: find all parsers/collectors that read AI coding-agent usage data (tokens, cost, sessions) from local files/logs - e.g. Claude Code, Codex, Cursor, GitHub Copilot, Gemini CLI, Aider, etc. Likely under src/main/... in packages named something like "parser", "provider", "usage", "stats", "collector".

For each parser found report:
- file path
- what agent/tool it parses (Claude Code, Cursor, Codex, etc)
- what data source format it reads (jsonl log file, sqlite db, config file, API) and where on disk
- key class/function name and brief description of parsing logic (how it extracts token counts / cost / session info)

List ALL parsers found, do not skip any. Also note directory structure of src/main to help me get oriented (list top-level packages under main source once). Keep answer organized as a list per parser, thorough but not verbose in prose.