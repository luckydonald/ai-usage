In this repo (/home/user/git/luckydonald/ai-usage), two things to research:

1. Claude "statusline" provider: find where it's implemented (likely src/ai_usage/providers/claude.py or similar), how it currently gets usage data, and how staleness is detected/could be detected, so it could "fall back to cli-usage if stale for too long." Look for any existing staleness/freshness checks elsewhere in the crawler.

2. "Record the used model where available with the usage": find the data model for usage samples/events (likely a dataclass or pydantic model in src/ai_usage/, and the storage format e.g. jsonl files), to see whether there's already a field for model name, and how hard it'd be to add one. Check ai/references/console-output/claude/motd/normal-team.txt and ai/references/console-output/codex/motd/normal.md if they exist, to see what model info looks like in the raw CLI output.

Report file:line for key structures, under 400 words total.