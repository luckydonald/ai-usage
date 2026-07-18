Repo /home/user/git/luckydonald/ai-usage. Read-only research only, no edits.

Context: `CodexStatusProvider` in src/ai_usage/providers/codex.py scrapes the `codex` CLI's `/status` output via pexpect. That output can include a line like:
```
Warning:              limits may be stale - run /status again shortly.
```
User wants: when this warning line is present, the crawler should recrawl this account after 10 seconds (instead of waiting for the normal crawl interval).

Investigate and report:
1. Read src/ai_usage/providers/codex.py fully — specifically `CodexStatusProvider.fetch()`, `run_codex_status()`, `parse_codex_status()`, `STATUS_PATTERN`. Does it currently parse/detect the "Warning: limits may be stale" line at all? Show exact current regex and parsing logic.
2. Find the crawl scheduler — likely uses `fastscheduler` dependency (grep pyproject.toml/imports) or a custom loop. Find the file(s) that call `provider.fetch()` on an interval (crawler.py, scheduler.py, runtime.py, or similar). Report: how is the interval for a given account determined, is there any existing mechanism for a provider/fetch result to request "run me again sooner" (e.g. a field on ProviderFetchResult, or a return value, or an exception type), and how the scheduler loop is structured (asyncio tasks, fastscheduler Job objects, etc).
3. Report the ProviderFetchResult model (models.py) fully — all fields — so we know whether adding something like `next_fetch_delay_seconds: float | None` would fit naturally, or whether there's already a similar field (e.g. related to `status: FetchStatus` stale/partial).
4. Report any existing "backoff" or "retry sooner" logic anywhere in the crawler for error cases, as precedent for how a provider-driven early-recrawl signal might already be wired for errors and could be reused/extended for this warning case.

Keep report tight, organized by the 4 points, cite file:line. Under 400 lines.