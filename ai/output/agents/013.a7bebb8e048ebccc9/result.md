Confirmed: no existing per-point/hover tooltip customization beyond ECharts' default `tooltip: { trigger: "axis" }` (frontend/src/chart.ts:123) — no `formatter`, no custom tooltip component. There's also no per-datapoint tooltip logic and no distinct tooltip handling for the max-block (markArea).

Here is the full report.

## 1. Frontend graph/chart code location

Stack: Vue 3 + TypeScript + Apache ECharts (`echarts` npm package), built with Vite/yarn.

- `/home/user/git/luckydonald/ai-usage/frontend/src/components/UsageChart.vue` — the chart component; owns the `echarts.ECharts` instance, mounts/resizes/disposes it, and calls `setOption`.
- `/home/user/git/luckydonald/ai-usage/frontend/src/chart.ts` — pure function `chartOption(...)` that builds the full ECharts `EChartsOption` (series, markArea, markLine, axes, tooltip, legend) from a `GraphSeries[]`. Also `seriesDisplayName`/`seriesKey` helpers.
- `/home/user/git/luckydonald/ai-usage/frontend/src/chart.test.ts` — unit tests over `chartOption` (vitest).
- `/home/user/git/luckydonald/ai-usage/frontend/src/App.vue` — top-level view: owns filters, time-range preset state, calls the API, wires the SSE `EventSource`, and passes `series`/`rangeStart`/`rangeEnd` down to `<UsageChart>`.
- `/home/user/git/luckydonald/ai-usage/frontend/src/time.ts` (+ `time.test.ts`) — time-range preset math (`rangeForPreset`, `customRange`, `wideningOrder`, etc.).
- `/home/user/git/luckydonald/ai-usage/frontend/src/api.ts` — `fetchCatalog`, `fetchLatest`, `fetchSeries` (all plain `fetch`).
- `/home/user/git/luckydonald/ai-usage/frontend/src/types.ts` — frontend TS types mirroring backend Pydantic models (`GraphPoint`, `GraphWindow`, `GraphSeries`, `Catalog`, etc).
- `/home/user/git/luckydonald/ai-usage/frontend/src/styles/` — SCSS.

Backend counterparts:
- `/home/user/git/luckydonald/ai-usage/src/ai_usage/api.py` — FastAPI routes: `/api/v1/catalog`, `/api/v1/latest`, `/api/v1/series`, `/api/v1/events` (SSE).
- `/home/user/git/luckydonald/ai-usage/src/ai_usage/graph.py` — turns raw `MetricSampleRecord` samples into `GraphSeries`/`GraphWindow`/`GraphPoint` (window/max-block computation, projection, colors).
- `/home/user/git/luckydonald/ai-usage/src/ai_usage/models.py:147-174` — Pydantic models `GraphPoint`, `GraphWindow`, `GraphSeries`.

## 2. Refresh/redraw mechanism (the "10s re-animation" bug)

There is no client-side `setInterval` polling. Instead:

- `App.vue:102-105` opens `new EventSource("/api/v1/events")` on mount and calls `void load()` (no `autoWiden`) every time a `"sample"` SSE event arrives.
- Backend SSE loop, `/home/user/git/luckydonald/ai-usage/src/ai_usage/api.py:160-184`: polls the DB for the newest `MetricSampleRecord` every iteration, and if the `event_id` changed since last loop, emits an `event: sample` SSE message; otherwise sends a `: keepalive`. The loop waits via `asyncio.wait_for(state.shutdown_event.wait(), timeout=2)` — i.e. checks every **2 seconds**, but only actually pushes a `sample` event when new data exists (which in practice arrives on whatever cadence the crawler samples usage, commonly ~10s in the wild — this is where the "every 10 or so seconds" symptom comes from; it's driven by new-data cadence, not a fixed frontend timer).
- Each `sample` event triggers `App.vue`'s `load()` (`App.vue:55-80`), which re-`fetchSeries(...)` and reassigns `series.value = await fetchSeries(...)` — a brand-new array/object graph every time, even if the underlying values are unchanged content-wise.
- `UsageChart.vue:63-67` has a `watch` on `[props.series, props.exhaustedColor, props.hiddenSeriesKeys, props.rangeStart, props.rangeEnd]` (deep) that calls `render(false)` on any change — so essentially every SSE-triggered reload calls `render(false)`.
- `render(recreate)` (`UsageChart.vue:28-52`): when `recreate` is `false` (the normal refresh path) it does **not** dispose/recreate the ECharts instance (`chart` is reused across calls; only `props.dark` changing calls `render(true)` which disposes+re-inits). It calls `chart.setOption(chartOption(...), recreate || isNew)` — so on refresh, `notMerge` is `false`, meaning ECharts merges the new option into the existing chart rather than fully recreating it.
- However, `chartOption()` (`chart.ts`) has **no top-level `animation: false`**, and none of the per-window "actual"/"reset"/"projection" series set `animation: false` (only the synthetic "now-line" series explicitly sets `animation: false` at `chart.ts:110` and `chart.ts:114`). Because `series.value` is a fresh array/object graph on every refresh (new `GraphPoint`/`GraphSeries` objects from `fetchSeries`), and the "actual" line's `data` array is rebuilt via `.map(...)` every call, ECharts treats this as new data on `setOption` and — with global animation enabled by default — replays the initial line-draw ("left-to-right") animation on every SSE-triggered refresh, not just on first load. This is the concrete mechanism behind the reported bug: the chart instance itself is not recreated, but the per-refresh `setOption` call re-triggers the initial-draw animation because animation is left on globally/per-series.

## 3. Max-block ("max-growth-box") rendering and the stray 100% line

Two distinct visual elements are relevant, both in `chart.ts`:

- **Max-growth-box** — drawn as a `markArea` on the "actual" series for every window in `item.windows` (`chart.ts:39-49`):
```ts
markArea: {
  silent: true,
  data: item.windows.map((window) => [
    { xAxis: window.start, yAxis: 0, itemStyle: { color: item.color, opacity: 0.16, borderColor: item.color, borderWidth: 1 } },
    { xAxis: window.end, yAxis: window.maximum_percentage },
  ]),
},
```
  This box's top edge sits at `window.maximum_percentage` (not 100), with a 1px border on all 4 sides (`borderWidth: 1`) — for every window, not just the current one.

- **Reset-boundary dotted line at y=100** — drawn only for `window.current === true` (`chart.ts:51-64`):
```ts
if (window.current) {
  rendered.push({
    id: `${item.account_id}/${item.metric_key}/reset-${index}`,
    ...
    data: [ [window.start, 100], [window.end, 100] ],
    lineStyle: { color: item.color, type: "dotted", opacity: 0.75 },
  });
  ...
}
```
  This is a horizontal dotted line drawn straight across the top of the chart (y=100%) spanning the *current* window's start→end, independent of the max-block's own top border. This is the most likely candidate for the "stray line at 100%" the user describes, since it only ever appears together with a current (i.e. visibly max-boxed) window, and its full-width placement at exactly y=100 matches "a stray line at the top of the graph."
  There is also a separate "exhausted" `markArea` (`chart.ts:88-102`) spanning `yAxis: 0` to `yAxis: 100` for windows where `window.exhausted_from` is set — that markArea's top border would also sit at exactly y=100 and could independently contribute a visible top-edge line whenever a window hit 100%.

Backend computation of the max-block data: `/home/user/git/luckydonald/ai-usage/src/ai_usage/graph.py`, function `build_windows()` (`graph.py:152-189`) — computes `start`, `end` (from `reset_at`/`window_seconds` or last sample), `maximum_percentage` (max of `percentage` in the window), `exhausted_from` (first sample reaching ≥100%), `current` (`end > now`), and `projected_end_percentage` via `projected_percentage()` (`graph.py:192-209`, a simple linear burn-rate extrapolation: `delta / elapsed * remaining`, clamped to `[last.percentage, 100]`).

## 4. Existing hover/tooltip code and available per-datapoint data

- Only config present: `tooltip: { trigger: "axis" }` at `chart.ts:123`. No `formatter`, no custom renderer, no per-series `tooltip` overrides, and several series are marked `silent: true` (the markLine "now-line", the markArea overlays, the exhausted overlay) which by default suppresses hover interaction/tooltip triggering for those specific series — meaning the max-block/markArea currently cannot show any tooltip at all with the current config (silent areas don't participate in "axis" trigger tooltip content beyond the axis-aligned series values).
- Per-datapoint data available in `GraphPoint` (frontend `types.ts:53-58`, backend `models.py:147-152`): `at` (ISO timestamp), `percentage`, `current` (raw current usage value, nullable), `maximum` (raw maximum/limit value, nullable). Notably: no `provider`/`account`/`metric` fields on the point itself — those live one level up on `GraphSeries` (`service`, `provider`, `account_id`, `metric_key`, `metric_name`, `color`), so a tooltip formatter would need to correlate the hovered series `id`/name back to the parent `GraphSeries` object (already done for display name via `seriesDisplayName`/`seriesKey` in `chart.ts:5-11`).
- Per-window data available in `GraphWindow` (`types.ts:60-67` / `models.py:155-162`): `start`, `end`, `maximum_percentage`, `exhausted_from` (nullable timestamp of first ≥100% sample), `current` (bool), `projected_end_percentage` (nullable burn-rate projection). This is exactly the data needed for a max-block tooltip (burn-rate figure can be derived from `projected_end_percentage`/`maximum_percentage`/`start`/`end`/`now`; "100% reached" detection is `exhausted_from !== null`).
- Series ids in `chart.ts` follow the pattern `${account_id}/${metric_key}/actual`, `.../reset-{index}`, `.../projection-{index}`, `.../exhausted-{index}`, and the standalone `now-line` — these ids are how a tooltip `formatter` callback would need to distinguish which visual element (real data point vs. max-block vs. projection vs. reset-line) is being hovered.

## 5. Time-range/relative timeframe selection and future extension

- `/home/user/git/luckydonald/ai-usage/frontend/src/time.ts`:
  - `TimePreset` union: `"auto" | "1h" | "3h" | "6h" | "12h" | "day" | "week" | "month" | "year" | "all" | "custom"` (`time.ts:1`).
  - `rangeForPreset(preset, now)` (`time.ts:27-41`): for every relative preset, `end = now` exactly (no future extension at all) and `start = now - <duration>`. E.g. `"auto"` and `"1h"` both set `start = now - 1h`; `"week"` sets `start = now - 7d`; `"month"` uses `subtractCalendarMonth(now)`; `"year"` subtracts a UTC year; `"all"` sets `start = epoch (0)`. **`end` is always `now`, never extended into the future** — this is the gap the user's feature request targets ("graph should always display max(10% of selected timeframe, last closing of a window still running) into the future").
  - `wideningOrder` (`time.ts:43`) = `["1h","3h","6h","12h","day","week","month","year","all"]`, used by `App.vue`'s `load(autoWiden)` (`App.vue:67-73`) to auto-widen the range when a preset returns zero points (moves to the next wider preset and retries), but this only widens the *past* boundary, never touches the future direction.
  - `customRange(startText, endText)` (`time.ts:46-48`) builds an inclusive day range from date-only strings (both local midnight-to-midnight), used only for the `"custom"` preset.
- `App.vue:59-64`: computes `[start, end]` via `rangeForPreset`/`customRange`, stores into `rangeStart`/`rangeEnd` refs, which are passed straight through to `<UsageChart :range-start :range-end>` and from there into `chartOption(..., { start, end })`, which sets `xAxis.min`/`xAxis.max` directly to those timestamps (`chart.ts:130-134`) — so the x-axis is exactly `[rangeStart, rangeEnd]` with `end` always equal to "now" for relative presets; there is currently no logic anywhere computing "10% of the selected timeframe" or "the last still-open window's end" for extending the axis into the future.
- The only future-reaching element currently drawn is the red "now" markLine (`chart.ts:105-119`) and, for a `current` window, its `end` (reset time) and projection line data point at `window.end` (`chart.ts:56-86`) — but since `xAxis.max` is clamped to `rangeEnd` (== now for relative presets), any window/projection data past `now` is likely clipped off-screen today.

## 6. Data model for a measurement / window / limit block

Backend (Pydantic), `/home/user/git/luckydonald/ai-usage/src/ai_usage/models.py:147-174`:
```python
class GraphPoint(BaseModel):
    at: datetime
    percentage: float
    current: float | None = None
    maximum: float | None = None

class GraphWindow(BaseModel):
    start: datetime
    end: datetime
    maximum_percentage: float
    exhausted_from: datetime | None = None
    current: bool = False
    projected_end_percentage: float | None = None

class GraphSeries(BaseModel):
    service: str
    provider: str
    account_id: str
    metric_key: str
    metric_name: str
    color: str
    points: list[GraphPoint]
    windows: list[GraphWindow]
```
Frontend TS mirror, `/home/user/git/luckydonald/ai-usage/frontend/src/types.ts:53-78` (identical shape, `at`/dates as `string`).

Underlying raw sample/ORM data feeding `build_series`/`build_windows` comes from `MetricSampleRecord` in `/home/user/git/luckydonald/ai-usage/src/ai_usage/orm.py` (fields referenced in `graph.py`: `service`, `provider`, `account_id`, `metric_key`, `metric_name`, `observed_at`, `percentage`, `current_value`, `maximum_value`, `reset_at`, `window_seconds`, `event_id`) — worth reading directly if the plan needs to add new fields (e.g. burn-rate units) to the pipeline; not fully enumerated here since it wasn't requested, but it's the root source table for everything in `graph.py`.

Also relevant: `LatestMetric` (`types.ts:38-51`) is a separate, flatter per-metric "latest sample" shape (used for `/api/v1/latest` and the SSE payload via `record_payload` in `api.py`), distinct from `GraphPoint`/`GraphSeries` used for the chart itself.