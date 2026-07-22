In repo /home/user/git/luckydonald/ai-usage, find how logging is configured for the CLI (likely src/ai_usage/cli.py or a logging setup module). I need:
1. Is there already a --log-level or -v/verbose CLI option? File:line.
2. Where is logging.basicConfig or similar setup called, and what's the default level?
3. What logger names/hierarchy exist (e.g. "ai_usage", "ai_usage.providers.claude")?
4. Find all LOGGER.info(...) calls across src/ai_usage/ related to "crawling"/fetching/collecting status messages (e.g. in collector.py, progress.py) — file:line and message text — since I need to verify existing status messages already use INFO level vs some other level.

Read-only research, report file:line references and short snippets, no code changes.