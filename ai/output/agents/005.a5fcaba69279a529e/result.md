All findings confirmed. Answers:

**1. Existing `FetchStatus.STALE` handling in `collector.py`** (`src/ai_usage/collector.py:103-104`, inside `fetch_account`):
```python
if success and result.status == FetchStatus.STALE:
    self.report(f"{account.name}: {result.error} — reusing last known values.")
```
This runs *before* the normal success/failure branches (`elif success: ... else: Failed ...`). It does **not** substitute metrics from a previous fetch — the provider itself already returns the previously-known metrics in `result.metrics` (see claude.py below); collector just special-cases the reporter message so a STALE result is reported as "reusing last known values" instead of "Done fetching..." and, critically, never hits the `else: self.report(f"Failed {operation} ...")` branch. So STALE already bypasses "Failed" messaging today, independent of your crawler.py edit.

**2. Where "reusing last known values" text comes from**: it's built inline in that same `collector.py:104` f-string — `f"{account.name}: {result.error} — reusing last known values."` It depends on `result.error` containing the "no new statusline data yet (last update Xs ago)" text, which is set by the provider (see next point). There's no separate constant/template elsewhere; grep confirms this is the only source (also referenced in the plan doc `ai/plans/003_fix-claude-statusline-stale-relay-being-treated-as-a-crawl-e.md:27` as the target format).

**3. Confirmed: STALE is used by real providers today**, in two places:
- `src/ai_usage/providers/claude.py:127-133` — the Claude relay/statusline reader. When the relay file's age exceeds `stale_seconds` (default 120s), it returns `FetchStatus.STALE` with `metrics` still populated from the last-written relay payload, and `error=f"no new statusline data yet (last update {age:.0f}s ago)"`. This is exactly the string collector.py concatenates with "— reusing last known values."
- `src/ai_usage/providers/codex.py:246` — `status = FetchStatus.STALE if STALE_WARNING_PATTERN.search(output) else FetchStatus.SUCCESS`, triggered when codex's `/status` output contains "limits may be stale" (pattern at codex.py:21). Metrics are still parsed and included normally; only status flips to STALE. Note: `error` is NOT set here (no `error=` field passed), unlike claude.py's usage.

Also `crawler.py:114-121` (your edit) adds STALE handling in `update_state`: schedules a recheck in `STALE_RECHECK_SECONDS` (10s) and reports "limits reported as stale, rechecking in 10 seconds" — separate from collector.py's reporter message, operating on crawl scheduling not fetch reporting. And `cli.py:1088` also branches on `FetchStatus.STALE` (for display formatting, not read in detail here but confirms a third consumer).

**4. Your earlier claim was WRONG.** `FetchStatus.STALE` is not dead — it's an established status with real semantics already wired through three code paths before your crawler.py change:
- `claude.py`: relay data older than `stale_seconds` → STALE, carries forward last-known metrics + a "last update Xs ago" error string.
- `codex.py`: `/status` output flagging "limits may be stale" → STALE, metrics still current from this fetch (not carried-forward — codex just parsed them from live output, it's just labeling them potentially inaccurate).
- `collector.py:103-104`: turns STALE into a "reusing last known values" report line instead of "Failed"/"Done".
- `crawler.py` (your edit): schedules a 10s recheck for STALE results.

For your codex "limits may be stale" 10-second-recrawl case: it does **not conflict** — it's the same enum value with a consistent meaning ("this result is usable but may not reflect the freshest server-side state, retry soon"), and your crawler.py addition composes naturally with the existing collector.py reporter behavior. The test at `tests/test_progress.py:126-161` is exercising exactly this pre-existing collector.py branch (lines 103-104), not new behavior from your crawler.py edit — your crawler.py change is orthogonal (crawl scheduling), while the "no new statusline data yet"/"reusing last known values" wording comes from the claude.py provider + collector.py combo that already existed.