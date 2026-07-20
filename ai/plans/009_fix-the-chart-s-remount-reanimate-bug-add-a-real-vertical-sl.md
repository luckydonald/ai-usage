# Fix the chart's remount/reanimate bug, add a real vertical-slice tooltip

## Context
The usage chart still fully tears down and rebuilds its DOM node (and replays its entrance animation) on every live data refresh, causing a visible page jump — this has reportedly been "fixed" several times already at the ECharts-usage level without success, prompting the question of whether a different charting library would serve better. Separately, hovering the chart only shows the one series/point under the cursor; the user wants a full vertical time-slice (every series' value at that timestamp) instead. Three research agents (one reading the full `ai/query.md` history, one auditing the current ECharts feature usage, one tracing the actual bug) plus a validation pass and some library-comparison research went into this plan, so the findings below are evidence-based, not guesses.

## Root cause (confirmed, file:line precise)
The bug is **not** in the ECharts usage that was already patched twice (`UsageChart.vue`'s `render(recreate)` / merge-vs-notMerge logic is correct). It's one level up, in `frontend/src/App.vue`:
- `load()` (~line 74) unconditionally sets `loading.value = true`, awaits a real `fetchSeries()` network call, then `loading.value = false` in `finally`.
- The SSE handler (~line 139) calls `void load()` on **every** `sample` event — i.e. continuously during live use.
- The template (~line 245) is `v-if="loading" / v-else-if="error" / v-else-if="!series.length" / <UsageChart v-else>`.
- Flipping `loading` true→false around every await toggles that `v-if` chain, **unmounting** `<UsageChart>` (firing `chart?.dispose()`) and **remounting** a brand-new instance (fresh `echarts.init`, fresh `isNew` closure state) on every single refresh. That fresh-mount path forces `animate: true` and `notMerge: true` (see `UsageChart.vue`'s `render()`), which is exactly the reanimate-and-jump symptom. The two prior fixes never touched this because they only fixed the component's *internal* update path — which never gets a chance to run here, since the component itself is destroyed first.

## Should we switch charting libraries?
**No — stay on ECharts.** Two independent findings support this:
1. The bug above is a one-file, app-level `v-if`/loading-state bug, unrelated to the charting library. Migrating would not fix it by itself.
2. The current codebase leans on ECharts-specific capabilities that most lighter alternatives don't replicate out of the box: custom-shaped `markArea` regions carrying passthrough tooltip data (`windowIndex`/`noteIndex`) for window backgrounds, exhausted-region highlighting, and notes/promo bands; `markLine` for the "now" line; a `legend` with scroll + selected-state sync; per-series animation overrides; manually-bounded time axis; built-in dark theme. Web research confirms: `uPlot` (~20-45KB) is faster and lighter but "Spartan," low-level, no legend model, no shaded-region-with-custom-tooltip primitive — would mean hand-building canvas overlays for everything `markArea` gives for free today. `lightweight-charts` is finance/candlestick-focused with a similar gap. `ApexCharts`/`Chart.js` have annotation plugins but nothing as flexible as `markArea` for this exact combination of freeform regions + custom hover content. None of them clearly beat ECharts here without a large, risky rewrite for uncertain gain.
3. **Also in scope now**: the app currently does `import * as echarts from "echarts"` (full bundle, ~1.24MB/420KB gzip, flagged by the Vite build warning) instead of the tree-shaken `echarts/core` + `echarts.use([...])` pattern. User opted to switch to tree-shaken mode as part of this pass (Step 3 below) rather than deferring it.

## Requirements checklist (from `ai/query.md`, everything chart-related ever asked for)
Full extracted report is preserved in the session's research output; the headline items still open or newly relevant to this plan:
- Chart must not replay its draw-in animation on refresh; only genuinely new points may animate in. **(This plan)**
- Chart must not fully dispose/recreate its DOM node on refresh. **(This plan)**
- Hover overlay must show a full vertical slice (all series at that timestamp), not just one point. **(This plan, with the region-hover carve-out below)**
- Everything else (window/projection tooltip content and its several corrections, legend↔filter two-way sync, provider/account in legend and tooltip, data-point dot toggle, stray 100%-line bug, fixed x-axis range behavior, 5-color semantic palette, per-brand hue-based series colors, per-service info panels, range presets, "right on spot" easter egg) is **already implemented** in prior sessions — confirmed against the current code, not just the history log. Nothing further to do there as part of this plan.

## Decision: markArea region-hover vs. vertical-slice (user confirmed)
Hovering a window-background or notes-band markArea keeps today's detailed region tooltip (peak usage, burn rate, exhausted-at/blocked-for, projection text, promo text). Hovering anywhere else on the chart — including directly on a line's point — shows the new all-series vertical slice. This matches ECharts' natural split between item-hover (regions) and axis-trigger (time-slice), and avoids inventing a merged-tooltip mechanism ECharts doesn't cleanly support (confirmed via ECharts issue tracker: item-trigger-on-point + axis-trigger-elsewhere is a known, only-partially-supported combination that historically needs custom event wiring — this plan's implementation step below verifies actual behavior on the installed `echarts@^6` before finalizing).

## Implementation

### Step 1 — Decouple background refresh from the `loading`/`error` UI state (`frontend/src/App.vue`)
Split `load()` into a shared `performLoad({ autoWiden, silent })` core:
- Non-silent path (initial mount, preset/date/filter changes, the window-ends toggle) behaves exactly as today: sets `loading`, clears/sets `error`, runs `autoWiden` widening.
- New `loadSilently()` (used only by the SSE `sample` handler) calls the core with `silent: true`: never touches `loading`/`error`, so the `v-if` chain never flips and `<UsageChart>` never unmounts. On fetch failure, `console.error` and keep the last good chart on screen (no `error.value` write) — the next SSE tick retries naturally.
- `autoWiden` is hardcoded `false` for the silent path — auto-widening the preset is a first-load UX convenience; doing it silently mid-session would mutate the visible range-preset control with no feedback, which is worse than a temporarily-stale chart.
- All existing call sites keep calling `load()`/`load(true)` unchanged.
- Pre-existing "last write wins" race between a concurrent explicit `load()` and an in-flight `loadSilently()` is unchanged from today's behavior — not a regression, not fixed here.

### Step 2 — Axis-trigger vertical-slice tooltip, region tooltip preserved (`frontend/src/chart.ts`)
- Add `axisTooltipHtml(seriesList, paramsList, accountLabels)`: one shared timestamp header, one row per series reusing `pointTooltipHtml`'s per-series content (factor out a header-less `pointRowHtml` shared by both `pointTooltipHtml` — kept exported with its current signature/output so its existing unit tests keep passing — and the new axis function).
- Switch `tooltip.trigger` to `"axis"`. In the formatter, filter the incoming params array down to real data-point series (`Array.isArray(data) && data.length === 2`) before building rows, excluding the synthetic `now-line`/`notes-marker`/`exhausted-*`/`projection-*` series so they don't inject blank or duplicate rows. Decide during implementation whether the dashed projection line should contribute its own row in the slice or stay excluded (UX call, not yet made — surface it during implementation rather than guessing here).
- **Required verification step before finalizing this behavior** (do not assume from docs alone): run the frontend locally (`ai-usage serve` and/or `yarn dev` in `frontend/`) with the browser tool, hover a bare line point (expect the new multi-series slice), then hover inside a window markArea and a notes band (expect today's existing region tooltip to still fire). Inspect the actual `params` shape ECharts hands the formatter in each case on the installed `echarts@^6.0.0` — the exact mechanics of item-hover-on-markArea coexisting with axis-trigger-elsewhere are not fully documented and must be confirmed live. If region tooltips stop firing under `trigger: "axis"`, fall back to per-markArea-data-item `tooltip.formatter` overrides or a manual `mouseover`/`mouseout` floating tooltip for markArea, keeping axis-trigger for everything else — but only go there if the default combination actually breaks.
- Keep `axisPointer: { show: true, type: "line" }` (already configured) as the crosshair.

### Step 3 — Tree-shaken `echarts/core` import (in scope for this pass; still its own commit)
Swap `import * as echarts from "echarts"` for `echarts/core` + explicit `echarts.use([LineChart, GridComponent, LegendComponent, TooltipComponent, MarkAreaComponent, MarkLineComponent, CanvasRenderer])` (covers every feature the catalog confirmed is actually used — no dataZoom/toolbox/brush/visualMap/map/radar in use anywhere). Verify the built-in `"dark"` theme name still resolves in the modular build (may need an explicit theme import/registration). Keep this as its own commit with its own full manual smoke pass (dark mode, tooltip, legend, markArea shading, "now" line, resize) even though it's done in this same pass — a missing `.use()` registration fails at runtime with an easy-to-miss warning, not a compile error, so keep it isolated from Steps 1–2 for easy bisection if something regresses.

## Critical files
- `frontend/src/App.vue` — `load()`/`loadSilently()` split, SSE handler.
- `frontend/src/chart.ts` — `pointRowHtml`/`axisTooltipHtml`, `tooltip.trigger` change, formatter rewrite.
- `frontend/src/chart.test.ts` — existing `pointTooltipHtml`/`windowTooltipHtml` tests must keep passing unchanged; add tests for the new axis-trigger multi-series formatter and for the synthetic-series filtering.
- `frontend/src/components/UsageChart.vue` — no change expected (its merge/no-reanimate logic is already correct; it just needs to stay mounted).
- `frontend/vite.config.ts` — only touched in Step 3.

## Verification
- `yarn vitest run`, `yarn vue-tsc --noEmit`, `yarn build` after each step.
- Manual: run `ai-usage serve` against real data, use browser automation to watch a live SSE tick and confirm no DOM-node replacement / no reanimation (check via `read_console_messages`/network + visual screenshot before/after a tick), then hover-test the three tooltip modes (bare point → slice, window region → region tooltip, notes band → region tooltip) per Step 2's required verification.
- No backend changes; no migrations; no new dependencies unless Step 3's `echarts/core` split needs an explicit theme package.
