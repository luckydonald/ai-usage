Report ready.

**Directive:** Research frontend files/graphs/colors/date-range/reset-to-0%/App.vue structure. No edits made.

**1. Files under `frontend/src`:**
- `App.vue` (140 lines) — root: header, latest-metric cards, filter sidebar, graph panel, theme toggle, SSE live-refresh.
- `api.ts` — `fetchCatalog`/`fetchLatest`/`fetchSeries` HTTP calls.
- `chart.ts` — builds echarts `option` object (series lines, exhausted-zone markers, axis styling).
- `chart.test.ts`, `time.test.ts`, `main.test.ts` — unit tests.
- `components/UsageChart.vue` — wraps echarts, watches series/dark/exhaustedColor/hidden keys/range props.
- `time.ts` — `TimePreset` type + `presetLabels` + `rangeForPreset()` + `wideningOrder`.
- `types.ts` (86 lines) — `Account`, `Catalog`, `GraphSeries`, `GraphWindow`, `Filters`, etc.
- `sentry.ts`, `main.ts`, `env.d.ts`, `views/SentryTestView.vue`, `styles/main.scss`.

**2. Charting:** echarts (`"echarts": "^6.0.0"` in package.json), custom option-builder in `chart.ts`. Colors: server-assigned. `src/ai_usage/api.py:151-157` builds `colors: dict[(account_id, metric_key)] = color` from `AccountConfig.colors` (`models.py:112`, `dict[str,str]`), passed to `graph.py: build_series()`. `graph.py:66` uses configured color or falls back to `generated_color("/".join(identity))` (deterministic hash-based color) — this is the "one base brand color, distinguishable per account" mechanism, currently generic, not brand-mapped. `GraphSeries.color` (types.ts:75) is the resolved per-line color reaching the frontend; `chart.ts:37-38` applies it to lineStyle/itemStyle. `exhausted_color` is a single global catalog-level color (types.ts:35), used for the "exhausted" zone marker (chart.ts:97).

**3. Date range:** No date-picker library in package.json. `time.ts` only has fixed presets (`auto/1h/3h/6h/12h/day/week/month/year/all`) via `rangeForPreset()`, no custom-range/calendar UI at all. `App.vue:111` renders presets as a plain `<select>`.

**4. Window % reset to 0%:** No client-side ticking recompute found — `GraphSeries.windows: GraphWindow[]` (types.ts:60-67, fields: `start/end/maximum_percentage/exhausted_from/current/projected_end_percentage`) is precomputed server-side per fetch (`build_series` in `graph.py`) and just rendered/watched in `UsageChart.vue`. Latest-card % (`App.vue:104`) comes from `fetchLatest()` (`LatestMetric.percentage`), also server-computed, no client formula recalculating post-reset_at. So "auto-zero after window end" isn't currently live-ticking anywhere client-side; it's whatever `latest`/`series` return on next poll/SSE `sample` event (`App.vue:84`).

**5. App.vue sections:** header (title + theme toggle) → exposed-without-auth warning banner → `main`: (a) `cards` section = latest-metric tiles, (b) `workspace` = `aside` filter sidebar (Range/Services/Providers/Accounts/Metrics multi-selects) + `graph-panel` (loading/error/empty states, else `<UsageChart>`). That's the entire UI — a "remove everything except graphs" rebuild would gut the cards section, filter sidebar, and the plain preset select, keeping only `UsageChart.vue`/`chart.ts` as the base to rebuild around.