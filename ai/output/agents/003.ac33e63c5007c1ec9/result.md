## 1. Codex "stale limits" warning — currently NOT detected

`src/ai_usage/providers/codex.py`

- `STATUS_PATTERN` (lines 15-19):
  ```python
  STATUS_PATTERN = re.compile(
      r"(?P<name>Weekly|\d+\s*hour)\s+limit:\s+.*?(?P<remaining>\d+(?:\.\d+)?)%\s+left\s+"
      r"\(resets\s+(?P<reset>[^)]+)\)",
      re.IGNORECASE,
  )
  ```
  This only matches the `Weekly limit: … % left (resets …)` / `N hour limit: …` lines. There is no pattern, string search, or flag anywhere for `"Warning:"` / `"limits may be stale"`.

- `parse_codex_status()` (lines 204-221): iterates `STATUS_PATTERN.finditer(output)` and builds `Metric` objects only. No inspection of the raw `output` for a warning substring, no extra return value.

- `run_codex_status()` (lines 255-270): spawns `codex` via pexpect, sends `/status` twice, then `/quit`, and returns `child.before` (all the terminal text captured up to the final `EOF` match) as one big string. So the warning line, if emitted, is present in this string, but nothing downstream looks for it.

- `CodexStatusProvider.fetch()` (lines 232-251): calls `run_codex_status`, then `parse_codex_status`, raises `ProviderError` if no metrics were found, and otherwise returns a plain `ProviderFetchResult` with default `status=FetchStatus.SUCCESS`. There is no code path that would set a shorter next-fetch delay.

**Conclusion: the "stale" warning is completely unhandled today** — it's neither parsed nor used to influence scheduling.

## 2. Crawl scheduler

Uses `fastscheduler` (`from fastscheduler import FastScheduler`, `src/ai_usage/crawler.py:7`). `pyproject.toml` lists it as a dependency.

Structure (`src/ai_usage/crawler.py`):
- `Crawler.run()` (149-168) starts a `FastScheduler` with a 1-second tick (`self.scheduler.every(1).seconds.no_catch_up().do(self.tick)`), then just sleeps forever in an asyncio loop — all actual scheduling logic is custom, driven by DB state, not by fastscheduler job intervals.
- `Crawler.tick()` (64-85): every second, loads accounts, ensures a `CrawlStateRecord` exists per account (`next_run_at` defaults to now), computes `due` = accounts whose `state.next_run_at <= now`, then calls `self.collector.fetch_all(due, ...)` and for each `(account, result)` pair calls `update_state`.
- `Crawler.update_state()` (87-147) is where the **next run time is computed** — this is the natural place to plug in the new warning-driven behavior:
  - On `result.status == FetchStatus.ERROR` (100-111): exponential backoff — `next_run_at = now + min(maximum_backoff_seconds, active_seconds * 2**failure_count)`.
  - Otherwise (112-144): normal path — computes `percentage` from `result.metrics`, decides if usage increased (extends "active" window), then sets `interval = active_seconds if currently active else normal_seconds`, applies `jitter = uniform(0.95, 1.05)`, and sets `state.next_run_at = now + timedelta(seconds=interval * jitter)`.

**Interval determination**: `self.config.intervals_for(account)` (`src/ai_usage/config.py:131`) returns a dict with defaults (from lines 13-16): `normal_seconds=600`, `active_seconds=60`, `active_for_seconds=900`, `maximum_backoff_seconds=3600`. These can presumably be overridden per-account via `AccountConfig.intervals` (models.py:83).

**Is there an existing "run me again sooner" mechanism on the result itself?** No. `ProviderFetchResult` (see #3) has no delay/hint field. The only two signals the scheduler currently reacts to are:
1. `result.status == FetchStatus.ERROR` → backoff formula (not "sooner", it's a growing delay).
2. `usage_increased` (computed from `result.metrics` percentages, not from the result object directly) → switches to the shorter `active_seconds` interval for `active_for_seconds`.

There is no return value, field, or exception type used today to let a provider request an arbitrary custom delay like "recheck in exactly 10 seconds."

## 3. `ProviderFetchResult` (full model)

`src/ai_usage/models.py:61-69`:
```python
class ProviderFetchResult(BaseModel):
    service: str
    provider: str
    account_id: str
    fetched_at: datetime
    status: FetchStatus = FetchStatus.SUCCESS
    metrics: list[Metric] = Field(default_factory=list)
    error: str | None = None
# end class
```
`FetchStatus` (models.py:10-14) is a `StrEnum`: `SUCCESS`, `PARTIAL`, `ERROR`, `STALE`.

Notably **`FetchStatus.STALE` already exists as an enum value but is never used anywhere** — I grepped and it's not referenced in crawler.py, collector.py, or any provider. It's currently dead/unused. This is a strong existing hook: the codex stale-warning case maps semantically almost exactly onto `FetchStatus.STALE`.

There is no field like `next_fetch_delay_seconds` today. Adding one (e.g. `next_fetch_delay_seconds: float | None = None`) would fit cleanly next to `error: str | None = None` — same optional/None-default style. Alternatively/additionally, wiring `FetchStatus.STALE` into `update_state()`'s branching (alongside the existing `ERROR` branch) would reuse an already-defined-but-dormant concept instead of adding a new field.

## 4. Existing backoff / retry-sooner precedent

Only one precedent exists, and it's a *slow-down*, not a *speed-up*: the `FetchStatus.ERROR` branch in `update_state()` (`src/ai_usage/crawler.py:100-111`):
```python
if result.status == FetchStatus.ERROR:
    state.failure_count += 1
    backoff = min(
        intervals["maximum_backoff_seconds"],
        intervals["active_seconds"] * (2 ** state.failure_count),
    )
    state.next_run_at = now + timedelta(seconds=backoff)
    state.last_error = result.error
    self.report(...)
```
This is driven purely by `result.status` (an enum on `ProviderFetchResult`) plus persisted `CrawlStateRecord.failure_count` — no provider-supplied numeric delay is read from the result. The only other interval-shortening precedent is the unrelated "usage increased → switch to `active_seconds`" logic (112-135), which is also derived from metrics content, not a direct field on the result.

**No existing mechanism lets a provider directly say "recrawl me in exactly N seconds."** Implementing the requested 10-second-after-stale-warning behavior would require either:
- (a) adding a new optional field to `ProviderFetchResult` (e.g. `next_fetch_delay_seconds` or reusing `FetchStatus.STALE`) that `CodexStatusProvider.fetch()` sets when it detects the warning line (would need a new regex/substring check for `"Warning:"` / `"limits may be stale"` in the raw pexpect output, separate from `STATUS_PATTERN`), plus
- (b) a new branch in `Crawler.update_state()` that checks this field/status before falling through to the normal-interval logic, setting `state.next_run_at = now + timedelta(seconds=10)` (or whatever the field specifies).

**Files/lines relevant to any such change:**
- `src/ai_usage/providers/codex.py:15-19` (STATUS_PATTERN), `204-221` (`parse_codex_status`), `232-251` (`CodexStatusProvider.fetch`), `255-270` (`run_codex_status`)
- `src/ai_usage/models.py:10-14` (`FetchStatus`), `61-69` (`ProviderFetchResult`)
- `src/ai_usage/crawler.py:87-147` (`update_state`, where the ERROR branch lives and a new STALE/delay branch would go)
- `src/ai_usage/config.py:13-16, 131` (`intervals_for` defaults, in case a configurable default like `stale_recheck_seconds` is wanted instead of a hardcoded 10)