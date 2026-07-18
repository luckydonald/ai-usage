Repo /home/user/git/luckydonald/ai-usage. Read-only.

I need to know: is `FetchStatus.STALE` already used/handled anywhere in `src/ai_usage/collector.py` (e.g. Collector.fetch_account) before my recent crawler.py edit? A test at tests/test_progress.py:126-161 (`test_stale_result_is_not_treated_as_a_crawl_failure`) asserts a provider returning `status=FetchStatus.STALE` causes a message containing "no new statusline data yet" and "reusing last known values", and asserts `"Failed crawling"` is NOT in messages.

Please grep/read collector.py fully and report:
1. Any existing handling of `FetchStatus.STALE` in collector.py — exact code, what it does (does it substitute in a previous fetch's metrics? does it change reporter messages?).
2. Where does "reusing last known values" text come from — grep for it repo-wide, show the exact call site and surrounding logic.
3. Confirm whether FetchStatus.STALE is used by any real provider today (e.g. claude.py's relay/statusline mechanism) — show that code if so.
4. Was my earlier research claim that "FetchStatus.STALE is currently dead/unused anywhere" WRONG? If so, explain what it's actually for, since I need to know if reusing it for codex's "limits may be stale" 10-second-recrawl case conflicts with its existing semantics.

Keep it tight, cite file:line, under 200 lines.