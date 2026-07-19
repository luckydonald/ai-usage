Repo: ai-usage, Vue3+TS+ECharts frontend at frontend/src/, FastAPI+SSE backend at src/ai_usage/.

Design implementation for these backlog items (from ai/plans/pending.md), all touching the usage chart:

### A. Bugs to fix
1. Chart re-plays left-to-right line-draw animation on every SSE refresh (every ~10s in practice), not just initial page load. Root cause (confirmed): App.vue's `load()` reassigns `series.value` to a brand-new array/object graph on every SSE "sample" event (frontend/src/App.vue:55-80, EventSource wired at App.vue:102-105). UsageChart.vue:63-67 watches `props.series` deep and calls `render(false)` (UsageChart.vue:28-52), which does `chart.setOption(chartOption(...), false)` — merge mode, chart instance NOT recreated. But chart.ts's `chartOption()` (frontend/src/chart.ts) has no top-level `animation: false`, and per-series "actual" line data is rebuilt via `.map()` every call, so ECharts treats it as new data and replays the initial draw animation. Only the synthetic "now-line" series explicitly sets `animation: false` (chart.ts:110,114). Need: initial page load keeps left-to-right draw-in animation, but subsequent SSE-triggered refreshes must NOT re-animate.
2. Stray line at top of graph (y=100%) whenever a max-growth-box (markArea) is displayed. Two candidate sources in chart.ts: (a) a dotted markLine drawn at y=100 spanning window.start→window.end for `window.current === true` windows (chart.ts:51-64) — "reset-boundary" line; (b) a separate "exhausted" markArea spanning yAxis 0→100 for windows where `exhausted_from` is set (chart.ts:88-102), whose top border sits at y=100. User wants this "stray line" removed. Determine which element is the actual unwanted line (likely the reset-boundary dotted line's visual appearance at exactly the top edge, or the border of the exhausted-area/markArea's default border rendering) and how to suppress just that line without losing legitimate info (the max-block itself, drawn via markArea at chart.ts:39-49 with top edge at window.maximum_percentage not 100, should stay).
3. Future-axis padding: on all relative time ranges, chart should extend the x-axis into the future by `max(10% of the selected timeframe duration, time until the last still-open/current window's end)`. Currently `rangeForPreset()` (frontend/src/time.ts:27-41) always sets `end = now` exactly for every relative preset, and chart.ts:130-134 sets `xAxis.max` directly to that `rangeEnd` — so nothing extends past "now" today (any window/projection data past now is clipped). Need this padding computed and applied — likely in time.ts's `rangeForPreset` or in App.vue where range is computed/passed to the chart, using `GraphWindow.end` data for "current" windows (available per series in chart.ts already, since it computes windows there) to find "the last closing of a window still running." Must NOT apply this to "custom" or "all" presets (open questions — use judgement, note as assumption).

### B. New feature: rich hover tooltips
Current tooltip config is bare: `tooltip: { trigger: "axis" }` (chart.ts:123) — no formatter, no custom rendering. Several series are marked `silent: true` (now-line, markArea overlays, exhausted overlay) which suppresses their own hover/tooltip participation entirely today.

Data available: `GraphPoint` (at, percentage, current, maximum — no provider/account, those live on parent `GraphSeries`: service, provider, account_id, metric_key, metric_name, color). `GraphWindow` (start, end, maximum_percentage, exhausted_from, current, projected_end_percentage). Full shapes in src/ai_usage/models.py:147-174 and frontend/src/types.ts:53-78.

Required tooltip content:

**On hovering a measurement point:**
- Timestamp
- Provider (e.g. codex/claude)
- Account (e.g. mail@example.com)
- Percentage
- Time until window end: window end time (absolute), relative time until then (e.g. "2h 32m"), and a percentage-through-window figure (0%=window start, 100%=window end, this is a *time* percentage, not the usage percentage — needs computing from `now`/window start/window end, or from the point's `at` if hovering a past point — clarify which in the plan)

**On hovering a max-block (markArea):**
- Window start and end time
- Usage percentage (the max-block's maximum_percentage)
- Average burn rate in %/time — but excluding the flat parts: don't count time before usage starts ramping up (~0% at start) or time after 100% is reached in the burn-rate average; user says "timeframe starts when activity happens so the start would count" (i.e. don't trim the start, only trim trailing flat-at-100% time)
- Conditional messaging based on whether/when 100% was reached:
  - If 100% reached before window end: show "hit 100% after X time" and "X time blocked" (time remaining after hitting 100% until window end)
  - If NOT reached by window end (widow ends >100%... actually window ends with value <100%, i.e. never exhausted): show remaining percentage at window end
  - If the very last datapoint is "exactly" 100% (within some tolerance) AND the time gap between the second-to-last point and the last point is not too large AND the gap between the last point and window end is not too large: show a "right on spot!" style message (Wii-Sports "perfect landing" vibe)
- Note: user separately described a near-identical "future graph" tooltip requirement (projections) with similar details plus "tells you to slow down or if you can do more work, and by which factor" — this is lower priority / more speculative; mention it as a follow-up phase, don't over-design it now, focus the concrete plan on the measurement-point and max-block tooltips above.

Constraints/conventions to respect:
- ECharts `tooltip.formatter` can be a function receiving params (series/data point being hovered) — need axis-trigger-compatible approach or switch relevant series to `trigger: 'item'` with per-series tooltip overrides; note current `silent: true` series won't trigger tooltip at all today, so hovering the max-block needs `silent: false` (or a different ECharts mechanism) on that markArea, weigh trade-offs (silent also currently prevents unwanted click/interaction side effects — check if removing silent introduces regressions e.g. blocking chart pan/zoom or other series' tooltips).
- Series id naming convention: `${account_id}/${metric_key}/actual`, `.../reset-{index}`, `.../projection-{index}`, `.../exhausted-{index}`, `now-line` — a tooltip formatter must distinguish which visual element triggered it via these ids.
- Existing test file frontend/src/chart.test.ts (vitest) covers `chartOption()` — plan should include what new/updated unit tests are needed there, and note that live browser verification (via claude-in-chrome or manual dev server run) will be needed since this is a visual/interactive frontend feature per project convention (UI changes must be exercised in a real browser before considered done).

Produce a concrete, file-by-file implementation plan: what changes in chart.ts, UsageChart.vue, App.vue, time.ts, and any backend model/graph.py changes needed (e.g. if burn-rate or percent-through-window needs backend computation vs frontend-only). Be decisive about the ECharts tooltip mechanism to use (custom formatter, trigger mode) rather than presenting several equally-weighted options. Keep it scoped to what's described above — do not invent unrelated improvements.