# Implementation Plan: Usage Chart Bug Fixes + Rich Hover Tooltips

## Scope decisions made up front (so the rest of the plan is unambiguous)

1. **No backend changes needed anywhere in this plan.** Everything required for the tooltip feature and the three bugs is already present in `GraphSeries`/`GraphWindow`/`GraphPoint` as returned by `/api/v1/series` (src/ai_usage/models.py, computed in src/ai_usage/graph.py). Burn rate, percent-through-window, and future-axis padding are all derivable client-side from `points`/`windows` already shipped. `src/ai_usage/graph.py` and `src/ai_usage/models.py` are **not touched**.
2. **Tooltip "Provider" field** — the user's example ("codex/claude") matches `GraphSeries.service`, not `GraphSeries.provider` (which holds an integration mechanism like `app-server`). The plan labels `item.service` as "Provider" in the tooltip to match the user's example, and treats this as a resolved naming assumption rather than an open question.
3. **Tooltip "Account" field** — `GraphSeries` only carries `account_id`; the human label (e.g. `mail@example.com`) lives in `Catalog.accounts[].identity`. This requires threading an `account_id -> label` map from `App.vue` down through `UsageChart.vue` into `chart.ts`.
4. **"now" vs "point's own time" for percent-through-window** — resolved: always compute relative to the hovered point's own `at`, never live `now`. This keeps the tooltip meaningful for points in closed/past windows (where "time until window end" from live `now` would be negative or nonsensical) and makes the number reproducible independent of when the user happens to be looking.
5. **Tooltip trigger mode** — switch `tooltip.trigger` from `"axis"` to `"item"`. This is required to reliably distinguish "hovering a point" vs "hovering a max-block" and to attach a custom formatter per element type. Trade-off: loses the synchronized cross-series vertical line that `trigger:"axis"` gives for free; mitigated by explicitly enabling `axisPointer` on the x-axis so a hover crosshair still shows. There is no `dataZoom` in the current chart, so making the max-block markArea non-silent does not risk breaking pan/zoom.
6. **Burn-rate trimming** — per the user's clarification, do **not** trim the leading flat period; only trim the trailing time after 100% was reached. Concretely: `elapsed = (exhausted_from ?? lastRelevantPointAt) - window.start`, `rate = (exhausted_from ? 100 : window.maximum_percentage) / elapsed`.
7. **"Remaining % at window end" message** only applies to **closed** windows (`window.current === false`) that never hit `exhausted_from`. For a still-open window that hasn't exhausted yet, only show the running peak/burn rate — no "at window end" framing since the window hasn't ended.
8. **"Perfect landing" thresholds** (concrete, tunable constants, since the request needs decisive numbers): last point's percentage within `±1` of 100 (`PERFECT_LANDING_TOLERANCE_PERCENT = 1`), and both "gap between second-to-last and last point" and "gap between last point and window.end" ≤ `15 minutes` (`PERFECT_LANDING_MAX_GAP_MS = 15 * 60 * 1000`). Documented as adjustable magic numbers.
9. **Future-graph/projection tooltip** (the "tells you to slow down / do more work, by which factor" idea) is explicitly deferred — not designed here beyond a one-line follow-up note.

---

## Bug 1 — animation replay on every SSE refresh

**Root cause confirmed** as described: `App.vue`'s `load()` reassigns `series.value` on every SSE "sample" event; `UsageChart.vue`'s deep watcher calls `render(false)` → `chart.setOption(option, false)` (merge mode, same instance). Since `chartOption()` has no top-level `animation: false`, ECharts replays entrance animation for the "actual" line series on every merge update.

**Fix — `frontend/src/chart.ts`**
- Add `animate?: boolean` to `ChartOptions` (default `true` when omitted, preserving existing test behavior).
- Add `animation: options.animate ?? true` to the top-level returned option object (alongside `backgroundColor`, `tooltip`, etc.).

**Fix — `frontend/src/components/UsageChart.vue`**
- In `render(recreate)`, the existing `isNew` flag already captures "this is a first paint or an explicit recreate." Pass `animate: recreate || isNew` into `chartOption(...)`'s options (this is exactly the same expression already used for the `notMerge` argument, so it's a one-line addition, not new state).
- Result: initial mount (`chart` is `undefined` → `isNew = true`) animates; SSE-triggered `render(false)` on an existing chart (`isNew = false`, `recreate = false`) does not; dark-mode toggle (`recreate = true`) still fully re-animates (acceptable, not the reported bug, not asked to change).

**Tests — `frontend/src/chart.test.ts`**
- Add: `chartOption(series, false, color)` (no `animate` passed) → `option.animation` is `true` (or the default is preserved).
- Add: `chartOption(series, false, color, { animate: false })` → `option.animation === false`.

**Browser verification**: run dev server, watch the chart across two SSE "sample" events (or manually re-trigger the watcher) and confirm no left-to-right redraw after the first paint, while a hard reload still shows the draw-in animation.

---

## Bug 2 — stray line at y=100% on the max-block

**Determination**: the culprit is candidate (a), the `reset-{index}` series (`frontend/src/chart.ts:53-64`), not the exhausted markArea (b). Reasoning:
- The exhausted markArea (chart.ts:88-102) only sets `itemStyle.color`/`opacity` — no `borderWidth`/`borderColor` — and ECharts markArea `itemStyle.borderWidth` defaults to `0`, so it renders no border line at all today.
- The `reset-{index}` series draws an explicit dotted line at literal `yAxis: 100` across the *entire* current window's start→end, **independent of whether the max-block ever approached 100%**. This is exactly "a stray line at the top of the graph at y=100%": it appears for every current window regardless of actual usage level, sitting right on top of (and visually indistinguishable from) the chart's own y-axis-max=100 border.
- The user's own framing ("max-growth-box is displayed") lines up because in practice the reset line is only visible where the max-block (which is drawn for every window, not just current ones) is also currently shown — the current window's max-block is the one usually in view.

**Fix — `frontend/src/chart.ts`**
- Delete the `rendered.push({ id: ".../reset-${index}", ... })` block (lines ~53-64) entirely. Keep the `windowStart`/`windowEnd`/`last` computation below it (lines ~65-72) since the projection-line logic (`.../projection-${index}`) still needs it.
- Leave the max-block markArea (lines 39-49, top edge at `window.maximum_percentage`) and the exhausted markArea (lines 88-102) untouched — both are explicitly meant to stay per the requirement.

**Tests — `frontend/src/chart.test.ts`**
- Update the first test ("renders actual steps, reset boundary, projection, and a now-line"): rename/adjust to reflect 3 series (`actual`, `projection-0`, `now-line`) not 4; update the `toHaveLength(4)` → `toHaveLength(3)` and index-based assertions (`rendered[2]` for projection-0 becomes `rendered[1]`, `rendered.at(-1)` for `now-line` unchanged).
- Other tests (grouping by legend name, projection anchoring, x-axis range) are unaffected by removing the reset series but should be re-run to confirm indices/lengths implicitly assumed elsewhere aren't broken.

**Browser verification**: load a series with a current window, confirm no dotted line sits along the top edge of the plot; confirm the max-block (shaded area) still renders with its own top edge at the correct (non-100) percentage, and the exhausted overlay (if any sample hit 100%) still renders.

---

## Bug 3 — future-axis padding for relative ranges

**Fix — `frontend/src/time.ts`**
- Add a new exported pure function, e.g.:
  ```ts
  export function paddedChartEnd(
    preset: TimePreset,
    start: Date,
    end: Date,
    series: GraphSeries[],
  ): Date
  ```
- Behavior:
  - If `preset === "custom" || preset === "all"`, return `end` unchanged (explicit exclusions from the requirement).
  - Otherwise: `duration = end.getTime() - start.getTime()`; `tenPercent = duration * 0.1`; find `lastCurrentWindowEnd = max over all series, all windows where window.current === true, of new Date(window.end).getTime()` (or `undefined` if none); `timeUntilLastWindowEnd = lastCurrentWindowEnd ? Math.max(0, lastCurrentWindowEnd - end.getTime()) : 0`; `padding = Math.max(tenPercent, timeUntilLastWindowEnd)`; return `new Date(end.getTime() + padding)`.
- This needs `GraphSeries`/`GraphWindow` types imported from `./types` (already used elsewhere in this module's neighbors, e.g. `chart.ts`).

**Fix — `frontend/src/App.vue`**
- In `load()`, after `series.value = await fetchSeries(start, end, filters)` (and after `pruneHiddenSeriesKeys()`/the `autoWiden` branch, so it uses the final resolved `series.value`), set:
  ```ts
  rangeStart.value = start;
  rangeEnd.value = paddedChartEnd(preset.value, start, end, series.value);
  ```
  replacing the current unconditional `rangeEnd.value = end;` line. Keep the **fetch** call itself using the original unpadded `end` (no reason to query the backend for a future window; current-window data with `window.end` beyond `now` is already returned regardless of the query's `end`, per `src/ai_usage/graph.py`'s window building, which is independent of the query range).
- No change needed in `chart.ts` itself — `xAxis.max` already just uses `options.end` (chart.ts:133), which will now receive the padded value from `UsageChart.vue`'s `rangeEnd` prop.

**Tests — `frontend/src/time.test.ts`**
- Add cases: (a) relative preset with no current windows → padding is exactly 10% of duration; (b) relative preset where a current window's `end` is further out than 10% of duration → padding equals the time to that window end; (c) `preset === "custom"` and `preset === "all"` → `paddedChartEnd` returns `end` unchanged regardless of window data.

**Browser verification**: pick an account/metric with a window whose reset is further out than 10% of the selected range (e.g. a 5-hour window on a "1 hour" preset), confirm the x-axis now extends visibly past "now" far enough to show the dashed projection line and the window's reset boundary, without extending on "All time"/custom ranges.

---

## Feature B — rich hover tooltips

### Data plumbing — `frontend/src/App.vue` → `frontend/src/components/UsageChart.vue` → `frontend/src/chart.ts`

- `App.vue`: build an `account_id -> label` map from `catalog.value.accounts`, reusing the existing `accountLabel()` helper (already used for filter chips, keeping the display convention consistent app-wide — email is shown when available since most accounts' `identity.email` is set):
  ```ts
  const accountLabels = computed<Record<string, string>>(() =>
    Object.fromEntries(catalog.value.accounts.map((account) => [account.id, accountLabel(account)])),
  );
  ```
  Pass as a new prop `:account-labels="accountLabels"` to `<UsageChart>`.
- `UsageChart.vue`: add `accountLabels: Record<string, string>` to `defineProps`, and pass it through in `render()`'s call to `chartOption(...)` as `options.accountLabels`.
- `chart.ts`: add `accountLabels?: Record<string, string>` to `ChartOptions`.

### `frontend/src/chart.ts` — markArea identification

- On the max-block markArea's boundary points (lines ~41-49), add a non-rendering identifying field carried through to tooltip params, e.g.:
  ```ts
  data: item.windows.map((window, index) => [
    { xAxis: window.start, yAxis: 0, itemStyle: {...}, windowIndex: index },
    { xAxis: window.end, yAxis: window.maximum_percentage, windowIndex: index },
  ]),
  ```
  (ECharts passes arbitrary extra keys on markArea coordinate objects through to `params.data` untouched; this is the same "smuggle metadata through the data object" idiom already implicitly relied on elsewhere — no rendering side effect since only `xAxis`/`yAxis`/`itemStyle` are interpreted for drawing.)
- Set the max-block markArea's `silent` to `false` (was `true` at chart.ts:40) so it participates in hover/tooltip. Leave the exhausted markArea's `silent: true` unchanged (out of scope; no tooltip requirement for it, and flipping it would risk double-firing tooltips when the exhausted area overlaps the max-block area for the same window).

### `frontend/src/chart.ts` — tooltip mechanism

- Change `tooltip: { trigger: "axis" }` to:
  ```ts
  tooltip: {
    trigger: "item",
    confine: true,
    formatter: (params) => tooltipFormatter(params, series, now, options.accountLabels ?? {}),
  },
  xAxis: {
    ...,
    axisPointer: { show: true, type: "line" },
  },
  ```
  where `tooltipFormatter` is a local function defined inside `chartOption()` (closing over `series`/`now`/`accountLabels`), dispatching on `params`:
  - `params.componentType === "markArea"` → look up the owning series via `series.find(s => seriesDisplayName(s) === params.seriesName)` (same reliable name-matching idiom `UsageChart.vue` already uses for `legendselectchanged`), read `windowIndex` off `(params.data as any)[0].windowIndex`, then call `windowTooltipHtml(matchedSeries, matchedSeries.windows[windowIndex], now, accountLabels)`.
  - `params.componentType === "series" && params.componentSubType === "line" && (params.data as unknown[]).length === 2` (a plain `[at, percentage]` tuple, i.e. the "actual" series, since silent reset/projection/exhausted series never fire) → look up series the same way via `seriesName`, get the point via `matchedSeries.points[params.dataIndex]`, find its window via a new `windowByPoint()` helper, and call `pointTooltipHtml(matchedSeries, point, matchingWindow, accountLabels)`.
  - Otherwise return `""` (no tooltip) — covers `now-line` and any future silent series.

### New exported pure helpers in `frontend/src/chart.ts` (unit-testable independent of ECharts/DOM)

```ts
export function windowByPoint(windows: GraphWindow[], at: string): GraphWindow | undefined;

export interface WindowStats {
  maximumPercentage: number;
  burnRatePerHour: number | null;      // null if <2 relevant points
  exhaustedAfterMs: number | null;     // window.start -> exhausted_from, only if exhausted
  blockedForMs: number | null;         // exhausted_from -> window.end, only if exhausted
  remainingPercentageAtEnd: number | null; // only for closed, never-exhausted windows
  perfectLanding: boolean;
}
export function computeWindowStats(points: GraphPoint[], window: GraphWindow, now: Date): WindowStats;

export function percentThroughWindow(pointAt: string, window: GraphWindow): number; // clamped 0-100, based on pointAt not now

export function pointTooltipHtml(item: GraphSeries, point: GraphPoint, window: GraphWindow | undefined, accountLabels: Record<string, string>): string;
export function windowTooltipHtml(item: GraphSeries, window: GraphWindow, now: Date, accountLabels: Record<string, string>): string;
```

- `formatDuration(ms: number): string` — new small helper (add to `frontend/src/time.ts` since it's a general-purpose formatting utility unrelated to ECharts, reusable/testable there): produces "2h 32m", "3d 4h", "45m", "<1m" style strings by picking the two largest non-zero units among days/hours/minutes.
- `computeWindowStats` implements the burn-rate rule from decision #6/#7/#8 above (trim only trailing flat-at-100% time; "remaining %" only for closed non-exhausted windows; "perfect landing" only under the two gap thresholds plus the ±1% tolerance).

### Tests — `frontend/src/chart.test.ts` (new)

- `windowByPoint`: point inside a window's `[start, end]` returns that window; point outside all windows returns `undefined`.
- `computeWindowStats`:
  - closed window, never exhausted → `remainingPercentageAtEnd === 100 - maximum_percentage`, `exhaustedAfterMs === null`.
  - window with `exhausted_from` well before `end` → `exhaustedAfterMs`/`blockedForMs` both set, `perfectLanding === false`.
  - window whose last point is ~100% with small gaps to previous point and to `window.end` → `perfectLanding === true`.
  - open/current window not yet exhausted → `remainingPercentageAtEnd === null` (per decision #7).
- `pointTooltipHtml`/`windowTooltipHtml`: smoke tests asserting the rendered HTML string contains the expected service/account/percentage/duration substrings for a fixed fixture (avoids over-specifying exact markup, just checks the key facts are present).
- Update the tooltip-config assertion(s) in the existing `chartOption()` tests if any previously asserted `tooltip: { trigger: "axis" }` shape (search for it; none currently do per the file read, so likely no change needed there beyond the animation/reset-line updates already listed above).

### Tests — `frontend/src/time.test.ts` (new)

- `formatDuration`: `0` → `"<1m"` (or similar), `150 * 60_000` → `"2h 30m"`, `26 * 3_600_000` → `"1d 2h"`.

### Browser verification (required — this is a visual/interactive change)

- Hover a measurement point on the "actual" line: confirm timestamp, provider (service), account label, percentage, window-end absolute+relative time, and percent-through-window all appear and are sane for both a recent point and an older/closed-window point (confirming the "based on point's own `at`" resolution reads correctly, not jumping around based on live time).
- Hover inside a max-block shaded area (not directly on the line): confirm the window-summary tooltip appears (proves `silent:false` + `markArea` hover works), shows start/end, peak %, burn rate, and the correct conditional message for: (a) an exhausted window with meaningful blocked time, (b) a closed window that never exhausted, (c) if reproducible, a near-100%-at-window-end case to see the "perfect landing" message.
- Confirm hovering the dashed projection line, the exhausted overlay, and the now-line produce no tooltip (still silent, out of scope), and that legend toggling / dark-mode toggle / SSE-driven refresh (from Bug 1's fix) don't regress alongside the new tooltip.
- Confirm `axisPointer` crosshair still shows on hover despite `trigger:"item"`, so panning across time visually still feels similar to before.

---

## Summary of touched files

- `frontend/src/chart.ts` — animation flag, remove reset-boundary series, tooltip formatter + new exported stats/formatting helpers, markArea metadata + `silent:false`, axisPointer.
- `frontend/src/components/UsageChart.vue` — pass `animate` flag into `chartOption`, add/pass through `accountLabels` prop.
- `frontend/src/App.vue` — compute padded `rangeEnd` via `time.ts`, compute and pass `accountLabels` map.
- `frontend/src/time.ts` — new `paddedChartEnd()` and `formatDuration()` exports.
- `frontend/src/chart.test.ts` — updated existing assertions (series count/order), new tests for animation flag, window stats, tooltip HTML.
- `frontend/src/time.test.ts` — new tests for `paddedChartEnd` and `formatDuration`.
- No backend files (`src/ai_usage/graph.py`, `src/ai_usage/models.py`, `src/ai_usage/api.py`) require changes.

### Critical Files for Implementation
- frontend/src/chart.ts
- frontend/src/components/UsageChart.vue
- frontend/src/App.vue
- frontend/src/time.ts
- frontend/src/chart.test.ts