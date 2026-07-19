Repo: ai-usage (local-first CLI/dashboard usage tracker for Claude/Codex/Copilot), at /home/user/git/luckydonald/ai-usage.

I need to plan a feature: the ongoing `crawl`/`up` commands (long-running processes that periodically poll configured provider accounts) should pick up changes to configuration — specifically:
- accounts added/removed via `provider add`/`provider login`/other CLI commands while crawl/up is already running (ideally live, or at least periodically re-read)
- the autocommit setting changing

Find and report (very thorough):
1. Where `crawl` and `up` commands are implemented (CLI entry points) — file paths.
2. How they currently load the list of configured accounts/providers at startup — is it a one-time read into memory, or do they re-read a config file/DB each loop iteration already?
3. What the config storage mechanism is (JSON file? SQLite? something else) — where accounts, credentials, and settings like "autocommit" live. File paths.
4. The main loop structure of crawl/up — how it schedules periodic fetches (asyncio loop, sleep interval, etc), so I know where a "reload config" step could be inserted.
5. Whether there's any existing file-watching, signal-handling (e.g. SIGHUP to reload), or config-reload mechanism anywhere in the codebase already.
6. Where "autocommit" setting is currently read/used and by what code path.

Report file paths, function/class names, and relevant snippets. Do not propose a design — just report current implementation so a plan can be written against real code.