In repo /home/user/git/luckydonald/ai-usage, investigate the "Claude /usage" statusline provider and its status-relay mechanism.

Read fully: src/ai_usage/providers/claude.py, src/ai_usage/crawler.py, and any code touching "relay_file", "install_status_relay", "remove_status_relay", "write_relay_payload", "ingest-claude" CLI command (in cli.py), and "ready"/"did not become ready" logic.

I'm debugging this error from ai/errors/1.txt:
```
Started crawling Claude /usage (claude/statusline, 72fc02a2-0e64-4cb4-89f9-e9e218a6ff07).
Failed crawling Claude /usage in 30.3s: Claude /usage did not become ready; use Claude once to refresh the status relay
Claude /usage: backing off crawl interval to 240 seconds after failure 2.
```

I need to understand:
1. What exactly "ready" means for this provider — what file/state does it check, and where's the exact code + message that raises "Claude /usage did not become ready; use Claude once to refresh the status relay"?
2. How the relay file is supposed to get populated (install_status_relay, write_relay_payload, ingest-claude command) — is it a statusline hook script installed into Claude Code's settings that calls back into `ai-usage ingest-claude`?
3. What Claude Code settings/hooks the install_status_relay function writes (check ~/.claude/settings.json if relevant, and check claude_relay_install CLI command in cli.py).
4. Whether the relay file currently exists on disk for account 72fc02a2-0e64-4cb4-89f9-e9e218a6ff07 (look under paths.local / "relay", likely ~/.ai-usage/local/relay/), and whether ~/.claude/settings.json actually has the statusline hook wired up currently.
5. Any timeout/staleness check (e.g. does it check relay file mtime, and how old is "stale"?).

Report back: exact file:line locations, the full logic path from "crawl this account" to "ready check fails", what's actually missing/misconfigured in this environment (e.g. relay file missing, statusline hook not installed, hook installed but Claude never invoked, hook installed but writes to wrong path, permission issue, etc.), and any relevant config file contents you read (settings.json statusline entry, account yml file for 72fc02a2..., relay file if present). Keep the report under 500 words, but include exact code snippets for the ready-check and the install function.