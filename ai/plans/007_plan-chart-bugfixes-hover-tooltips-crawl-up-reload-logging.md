# Plan: Chart bugfixes + hover tooltips, crawl/up reload logging

## Context

`ai/plans/pending.md` backlog huge, many unrelated items. Scoped this plan to 3 clusters user picked:
1. Graph bugs (animation replay, stray 100% line, future-axis padding)
2. Rich hover tooltips (measurement points + max-blocks)
3. crawl/up config-reload — investigation found this **already works** (no caching layer, everything reread every ~1s tick); only gap is it's silent. User asked: log the reload, be verbose generally.

Explicitly out of scope for this plan (noted for later, not touched): TUI-lib swap (user wants slim terminal-select lib, not full removal — separate task later), provider-add "hide already-discovered", cross-provider account merging, model recording, promo/notes tracking, Claude statusline fallback, "future graph" projection tooltip (deferred, see below).

Stack: Vue3 + TS + ECharts frontend (`frontend/src/`), FastAPI + SSE backend (`src/ai_usage/`). No backend changes needed for the graph work — everything derivable client-side from data already shipped in `GraphSeries`/`GraphWindow`/`GraphPoint`.

## Assumptions locked in (flag if wrong, otherwise proceeding as-is)

- Tooltip "Provider" = `GraphSeries.service` (e.g. "codex"/"claude"), not `.provider` (integration mechanism like `app-server`) — matches user's own example.
- "Account" label = `Catalog.accounts[].identity` via existing `accountLabel()` helper, keyed by `account_id`.
- Percent-through-window on point hover computed from the **hovered point's own `at`**, not live `now` — makes sense for closed-window points too.
- Burn-rate trims only trailing flat-at-100% time, never the leading ramp (per user: "timeframe starts when activity happens so the start would count").
- "Remaining %" message only for closed windows that never hit 100%. Open/current non-exhausted windows just show running peak + burn rate, no "at window end" framing.
- "Right on spot!" perfect-landing thresholds: last point within ±1% of 100, and both point-to-point gaps (prev→last, last→window end) ≤15min. Tunable constants, not user-specified numbers.
- Future-axis padding skipped entirely for `"custom"` and `"all"` presets.
- "Future graph" projection tooltip (burn-rate-based "slow down / do more work by factor X" messaging) — deferred, not designed here, one-liner follow-up only.

## A. Bug fixes (`frontend/src/chart.ts` etc.)

### A1. Animation replays every SSE refresh, not just first load
Root cause: `App.vue`'s SSE-triggered `load()` reassigns `series.value` to a fresh object graph every ~10s (whenever new sample data lands); `UsageChart.vue`'s deep watcher calls `render(false)` → `chart.setOption(option, false)` (merge, same instance) — but `chartOption()` has no `animation:false`, so ECharts replays entrance animation on every merge.

Fix:
- `chart.ts`: add `animate?: boolean` to `ChartOptions`, set top-level `animation: options.animate ?? true`.
- `UsageChart.vue`: in `render(recreate)`, pass `animate: recreate || isNew` into `chartOption(...)` (same expression already used for `notMerge`).
- Result: first paint and dark-mode toggle (`recreate=true`) still animate; SSE refresh on existing chart does not.

### A2. Stray line at y=100% when max-block shown
Culprit identified: the `reset-{index}` series (chart.ts ~L53-64) — a dotted line drawn at literal `yAxis:100` across every *current* window's full span, regardless of actual usage level. (Ruled out the exhausted-markArea as cause: it sets no `borderWidth`, so it draws no border today.)

Fix: delete the `reset-{index}` series block entirely. Keep the `windowStart`/`windowEnd`/`last` computation below it — still needed by the projection-line logic. Leave both markAreas (max-block, top edge at `window.maximum_percentage`; exhausted overlay) untouched.

### A3. Future-axis padding for relative ranges
Currently `rangeForPreset()` (`time.ts`) always sets `end = now` exactly; `chart.ts` sets `xAxis.max` straight to that — nothing extends past now.

Fix — new `frontend/src/time.ts` export:
```ts
export function paddedChartEnd(preset: TimePreset, start: Date, end: Date, series: GraphSeries[]): Date
```
- `preset === "custom" || "all"` → return `end` unchanged.
- else: `padding = max(10% of (end-start), time from end to the latest current-window's `window.end` across all series, floored at 0)`; return `end + padding`.

`App.vue`: after `series.value = await fetchSeries(...)`, set `rangeEnd.value = paddedChartEnd(preset.value, start, end, series.value)` instead of the current unconditional `rangeEnd.value = end`. Fetch call itself keeps using the unpadded `end` (backend already returns current-window data regardless of query range).

## B. Rich hover tooltips

### Data plumbing
`App.vue`: build `accountLabels: Record<string,string>` computed from `catalog.value.accounts` via existing `accountLabel()` helper → pass as new prop to `<UsageChart>`. `UsageChart.vue`: accept prop, forward into `chartOption(...)` as `options.accountLabels`. `chart.ts`: add `accountLabels?: Record<string,string>` to `ChartOptions`.

### Tooltip mechanism
Switch `tooltip.trigger` from `"axis"` to `"item"` (needed to distinguish point-hover vs max-block-hover and attach per-type formatting). Add `xAxis.axisPointer: { show:true, type:"line" }` to keep a hover crosshair despite losing axis-trigger's built-in one. No `dataZoom` present, so flipping the max-block markArea's `silent:false` (required for it to receive hover at all) carries no pan/zoom risk. Exhausted overlay's `silent:true` stays untouched (out of scope, avoids double-tooltip overlap).

Max-block markArea boundary points get an extra passthrough field `windowIndex` (ECharts forwards arbitrary extra keys on markArea coord objects to `params.data`, ignored for rendering) so the formatter can map back to the source `GraphWindow`.

`tooltip.formatter` dispatches on `params.componentType`:
- `"markArea"` → resolve owning `GraphSeries` via `seriesDisplayName` match on `params.seriesName`, pull `windowIndex` off `params.data[0]`, call `windowTooltipHtml(...)`.
- `"series"` line type with a 2-tuple data point (the "actual" series — silent series never fire) → resolve series the same way, get `GraphPoint` via `dataIndex`, find its window via new `windowByPoint()` helper, call `pointTooltipHtml(...)`.
- otherwise → `""` (now-line, projection, exhausted — no tooltip, unchanged).

### New pure/testable helpers (`chart.ts` unless noted)
- `windowByPoint(windows, at)` — window containing timestamp, or `undefined`.
- `percentThroughWindow(pointAt, window)` — 0-100 clamped, based on point's own `at`.
- `computeWindowStats(points, window, now)` → `{ maximumPercentage, burnRatePerHour, exhaustedAfterMs, blockedForMs, remainingPercentageAtEnd, perfectLanding }`, implementing the trimming/conditional rules from the locked assumptions above.
- `pointTooltipHtml(item, point, window, accountLabels)`, `windowTooltipHtml(item, window, now, accountLabels)`.
- `formatDuration(ms)` — new in `time.ts` (general-purpose, e.g. "2h 32m", "3d 4h", "<1m").

### Tooltip content
Point hover: timestamp, provider(service), account label, percentage, window end (absolute + relative "2h 32m" style), percent-through-window (N%).

Max-block hover: window start/end, peak %, burn rate (%/time, trailing-100%-trimmed), then one of: "hit 100% after Xtime" + "Xtime blocked" (exhausted before end) / remaining % at end (closed, never exhausted) / "right on spot!" (perfect landing case, overrides the exhausted message when applicable) / running peak only (still-open, not yet exhausted).

## C. crawl/up: log reload + general verbosity (new, from live feedback)

Investigation confirmed `Crawler.tick()` (`src/ai_usage/crawler.py`) already rereads `config.list_accounts()` and `git_backup_enabled()` fresh every ~1s tick — no caching layer exists, so add/remove/reauth and autocommit toggle already take effect live. Gap: none of this is logged, so it's invisible to the user running `crawl`/`up`.

Fix in `crawler.py`:
- In `tick()`, diff the just-fetched `accounts` list's ids against the previous tick's set (keep `self._known_account_ids: set[str]` on `Crawler`); log (`LOGGER.info`) any newly-appeared or disappeared account ids: `"account added: <service>/<account_id>"` / `"account removed: <service>/<account_id>"`.
- Track previous `git_backup_enabled()` result (`self._git_backup_was_enabled: bool | None`); log on change: `"git backup enabled"` / `"git backup disabled"`.
- General verbosity: audit `crawler.py`/`git_backup.py` for silent branches and add `LOGGER.info`/`LOGGER.debug` at key steps (tick start/summary — accounts due count, fetch results count; git backup attempt/skip/debounce reasoning) since user asked "be verbose generally." Ensure `logging.basicConfig`/level is actually configured so these show up — cross-check against the earlier-documented `LOGGER.warning` visibility mystery from webview_login.py session notes; verify with a real `crawl`/`up` run that new logs actually print, don't just assume.

Note: does NOT need `logging.basicConfig()` added blindly — first confirm current CLI logging setup (there may already be one for `crawl`/`up` specifically, distinct from the webview path) before adding one, to avoid duplicate handlers.

## Verification plan

- `frontend/src/chart.test.ts`, `frontend/src/time.test.ts`: update existing assertions (series count/order after removing reset-line), add new tests per section B/A3 above (animation flag, `paddedChartEnd`, `formatDuration`, `windowByPoint`, `computeWindowStats`, tooltip HTML smoke tests).
- Full test suite + ruff/lint before commit, per standing convention.
- **Required live browser verification** (frontend/UI convention): run dev server, confirm — no re-animation on SSE refresh but yes on hard reload; no stray 100% line while max-block still visible with correct top edge; x-axis visibly extends past "now" only on relative presets with a distant open window, not on custom/all; hovering a point shows full tooltip incl. correct account label and window-relative time; hovering inside (not on-line) a max-block shows the window summary with correct conditional message for an exhausted, a closed-never-exhausted, and (if reproducible) a near-100%-at-end window; legend toggle / dark mode / SSE refresh don't regress alongside new tooltip.
- **Required live crawl/up verification**: run `ai-usage crawl` (or `up`) in foreground, add an account via `provider add` in another terminal while it's running, confirm the new "account added" log line appears within ~1s; toggle `config git enable`/`disable` and confirm the log line appears; confirm no duplicate log lines/handlers from any `basicConfig` change.

### Critical files
- `frontend/src/chart.ts`, `frontend/src/components/UsageChart.vue`, `frontend/src/App.vue`, `frontend/src/time.ts`, `frontend/src/chart.test.ts`, `frontend/src/time.test.ts`
- `src/ai_usage/crawler.py` (+ check logging setup for `crawl`/`up` CLI entry points in `cli.py`)

## Todos

- [x] Git autocommit as toggleable global setting
- [x] Group CLI --help and separate internal tooling
- [x] Graph: force 0% after window ends
- [x] Custom date range picker
- [x] Frontend rebuild: strip to graphs-only + new palette
- [x] Shell completion staleness detection + versioned hashes
- [x] Claude/Codex web login via pywebview
- [x] Brand color generator per service
- [x] Fix animation replay on SSE refresh (A1)
- [x] Remove stray reset-line at y=100 (A2)
- [ ] Future-axis padding for relative ranges (A3)
- [ ] Hover tooltips: data plumbing + helpers (B)
- [ ] Update/add frontend tests
- [ ] crawl/up: log account add/remove + git-backup toggle (C)
- [ ] Live verification: browser (chart) + crawl/up logging
- [ ] Run full test suite + ruff, commit
