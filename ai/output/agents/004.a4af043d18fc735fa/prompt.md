Repo /home/user/git/luckydonald/ai-usage. Read-only research.

I just edited src/ai_usage/providers/codex.py (added STALE_WARNING_PATTERN, CodexStatusProvider.fetch now sets status=FetchStatus.STALE when pexpect output contains "limits may be stale") and src/ai_usage/crawler.py (Crawler.update_state now has an elif result.status == FetchStatus.STALE branch, setting state.next_run_at = now + timedelta(seconds=STALE_RECHECK_SECONDS) where STALE_RECHECK_SECONDS=10, resetting failure_count/last_error).

Find and report, so I can write matching tests:
1. Existing tests for `parse_codex_status`/`CodexStatusProvider` in tests/test_providers.py — show the exact test function(s) and fixture format used for pexpect-style status output strings, so I add one more test case with a "limits may be stale" line matching that same style.
2. Existing tests for `Crawler.update_state()` in tests (probably tests/test_crawler.py) — show how they construct a `ProviderFetchResult`, a `CrawlStateRecord`/DB session, and assert on `next_run_at`/`failure_count` after calling update_state, especially the existing FetchStatus.ERROR backoff test, so I can write an analogous FetchStatus.STALE test.
3. Confirm CrawlStateRecord field names (any DB setup helpers/fixtures needed to call update_state in isolation).

Report file paths, line numbers, and the relevant code verbatim (trimmed to essentials). Under 250 lines.