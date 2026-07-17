# Fix Claude statusline "stale relay" being treated as a crawl error (ai/errors/1.txt)

## Context

`ai/errors/1.txt` shows the crawler repeatedly failing to crawl the `claude/statusline` account (`72fc02a2-...`):

```
Failed crawling Claude /usage in 30.3s: Claude /usage did not become ready; use Claude once to refresh the status relay
Claude /usage: backing off crawl interval to 240 seconds after failure 2.
```

Root cause (`src/ai_usage/providers/claude.py:106-146`, `ClaudeStatusProvider.fetch`): the relay file is only useful when fresher than `stale_seconds` (default 120s). It's populated by a small standalone script (`install_status_relay`, `claude.py:207-259`) that Claude Code itself invokes on every statusline render — confirmed this is a real hook Claude Code calls directly (not `ai-usage` being invoked), so it only writes while an interactive Claude Code session is actively open and rendering. Whenever the crawler runs and no session has rendered a statusline in the last 2 minutes (the normal case for an unattended background crawler), the code falls through to `run_claude_usage`, spawning `claude` in a pexpect PTY and waiting up to 30s for `"Current session"` — a path that's unreliable outside a genuinely interactive terminal (confirmed separately: spawning `claude` from inside a sandboxed/nested session hits `"Remote Control failed · disabled by your organization's policy"` and never renders). It times out and raises `ProviderError`, which `Collector.fetch_account` (`collector.py:81-89`) turns into `FetchStatus.ERROR`, and `Crawler.update_state` (`crawler.py:88-98`) responds to with exponential backoff + an error report line.

This isn't really an error condition — it's just "no new data since last time," which the codebase already has a name for: `FetchStatus.STALE` (`models.py:10-15`) exists but nothing in `claude.py` ever produces it. `Crawler.update_state` only special-cases `FetchStatus.ERROR` (crawler.py:88) — anything else, including `STALE`, is treated as a normal successful tick (no backoff, interval resets normally). So the fix is purely in the provider: report staleness as `FetchStatus.STALE` with the last-known metrics instead of throwing, and only attempt the flaky pexpect fallback (or raise) when there has never been any relay data at all.

## Change

**`src/ai_usage/providers/claude.py`, `ClaudeStatusProvider.fetch` (lines 106-146):**

1. If `relay_file` is configured and exists, always parse it into `relay_metrics` (regardless of age).
2. If fresh (`age <= stale_seconds`): return `FetchStatus.SUCCESS` with `relay_metrics`, as today.
3. If stale but present: return `FetchStatus.STALE` with `relay_metrics` directly — do **not** attempt the pexpect fallback (it's slow and unreliable, and we already have real data, just a bit old).
4. If the relay file doesn't exist at all (never populated — e.g. account just added, no Claude session run yet): keep today's behavior, attempt `run_claude_usage` as a bootstrap, and raise `ProviderError` if that also fails.

**`src/ai_usage/collector.py`, `Collector.fetch_account` (~line 100-108):** when `result.status == FetchStatus.STALE`, report a distinct info line instead of the generic "Done fetching... N metrics", e.g.:
```
{account.name}: no new statusline data yet (last update {age}s ago) — reusing last known values.
```
so it's visibly informational, not lumped in with either "Done" or "Failed".

No changes needed to `run_claude_usage`, `parse_status_payload`, `parse_usage_output`, `install_status_relay`, or `Crawler.update_state` — the `STALE`-isn't-an-error behavior in the crawler already exists and just wasn't being exercised.

## Tests

Add to `tests/test_providers.py` (near `test_claude_status_line_payload`):
- Fresh relay file → `fetch` returns `FetchStatus.SUCCESS` with parsed metrics.
- Stale relay file (age > `stale_seconds`) → `fetch` returns `FetchStatus.STALE` with the same metrics, and `run_claude_usage`/pexpect is never invoked (monkeypatch it to raise if called, to prove it's skipped).
- No relay file, pexpect fallback failing → `fetch` still raises `ProviderError` with the existing message (bootstrap case unchanged).

Add to `tests/test_services.py` or wherever collector behavior is covered: a `STALE` result produces the new info-line report and is not counted as a crawl failure (i.e., verify `Crawler.update_state` doesn't back off for `STALE`, confirming existing behavior still holds after the provider change).

## Verification

- `uv run pytest tests/test_providers.py tests/test_services.py -q`
- Manually: `touch -d '2 hours ago' ~/.ai-usage/local/relay/72fc02a2-....json`, then `uv run ai-usage fetch --account 72fc02a2-0e64-4cb4-89f9-e9e218a6ff07` — should return instantly (no 30s hang) with the stale metrics and an informational (not error) message.
