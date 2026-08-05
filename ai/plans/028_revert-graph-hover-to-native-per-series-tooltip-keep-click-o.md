# Revert graph hover to native per-series tooltip; keep click overlay as-is

## Context

`chartOption()` in `frontend/src/chart.ts` currently drives ECharts' hover
tooltip with `trigger: "axis"` plus a custom `formatter` (`axisTooltipHtml`)
that groups *every* visible series at the hovered x-position into one big
badge/icon-laden HTML block. That was intentionally added so a single hover
could show "all entries at that time" — but it now feels heavy for the common
case of just skimming one line. The click-to-pin overlay
(`UsageChart.vue`'s `pinTooltip()` → `pinnedTooltipData` → the Vue-rendered
dialog) already covers the "all entries at this time" need and is unaffected
by this change — it calls `axisTooltipData()` directly, not the hover
formatter.

The ask: make **hover** behave like ECharts' native per-series tooltip
(trigger on the specific line/area under the cursor, not the whole
x-position), but keep our useful extras (native usage, reset-timing, window
peak/burn-rate/exhausted stats) — reshaped to fit a single-series tooltip
instead of the multi-group layout. Hovering a window's shaded background
block (`markArea`) should get equivalent treatment, and since a block and the
line drawn through it describe the same window, their hover content should
be built from one shared piece of logic rather than two parallel ones.

## Approach

### 1. Switch tooltip trigger to per-item (`frontend/src/chart.ts`)

In `chartOption()`'s `tooltip` block:
- `trigger: "item"` instead of `"axis"`.
- Replace the `formatter` callback: item-trigger formatters receive a single
  `CallbackDataParams`-shaped object (not an array). Keep `confine`,
  `extraCssText`, `backgroundColor`, `borderColor`, `textStyle` as-is.
- `xAxis.axisPointer` (the vertical line-follow) is independent of tooltip
  trigger mode and needs no change.

### 2. New dispatcher: `itemTooltipHtml()` (replaces `axisTooltipHtml`)

`axisTooltipHtml` (and its only caller, the old axis formatter) is deleted —
nothing else references it. `axisTooltipData()` / `buildAxisTooltipGroups()`
stay untouched; they still back the click overlay.

New function, keyed off `params.componentType` / `params.seriesId`:

```ts
export function itemTooltipHtml(
  seriesList: GraphSeries[],
  params: { componentType?: string; seriesId?: string; value?: unknown; data?: unknown },
  accountLabels: Record<string, string>,
  now: Date,
  notes: NoteRange[] = [],
): string
```

- `params.seriesId === "notes-marker"` → look up the hovered note via
  `(params.data as [{ noteIndex: number }])[0].noteIndex` and return
  `noteTooltipHtml(notes[noteIndex])` (unchanged existing helper).
- Otherwise parse `params.seriesId` (format `${account_id}/${metric_key}/actual`,
  set when pushing the main "actual" line series in `chartOption()`) to find
  the matching `GraphSeries` in `seriesList`.
- `params.componentType === "markArea"` → this is a hover on a window's
  shaded background. The window's `windowIndex` is already embedded in that
  markArea's data points (`chartOption()` already sets `windowIndex: index`
  on both boundary points of the "actual" series' window markArea — confirm
  while implementing that it's still on both, not just the start point).
  Read it off `(params.data as [{ windowIndex: number }])[0].windowIndex`,
  resolve `item.windows[windowIndex]`, and delegate to the existing
  `windowTooltipHtml(item, window, now, accountLabels)` (already exported,
  currently only exercised by tests — this wires it up for real).
- Otherwise (a line/point hover) → resolve the hovered instant from
  `params.value` (the `[point.at, point.percentage]` tuple set as the line's
  data) and delegate to a new `seriesPointTooltipHtml()` (see below).

### 3. New `seriesPointTooltipHtml()` — the "merged" line+window content

Replaces `pointTooltipHtml` (delete it; it's currently only exercised by
tests, no production caller). Reuses the existing per-point value/window
logic already written for the grouped hover (`pointAtOrBefore`,
`windowByPoint`, `isLastPoint`, `projectedValueAt`, `resetTiming`,
`resetTimingHtml`) — these stay as-is, just called from a single-series path
instead of `buildAxisTooltipGroups`'s loop-over-all-series path.

```ts
export function seriesPointTooltipHtml(
  item: GraphSeries,
  atMs: number,
  now: Date,
  accountLabels: Record<string, string> = {},
): string
```

Output shape (mirrors `windowTooltipHtml`'s header so the two feel like the
same tooltip family, per the "merge window and line" ask):

1. Header line: `${accountLabelFor(item, accountLabels)} · ${item.provider} · ${item.metric_name}` (same text `windowTooltipHtml` already uses).
2. Usage line: `Usage: <valueLabel><native usage in parens if present><reset-timing badges if a window is found>` — same value/projection logic currently inlined in `buildAxisTooltipGroups`.
3. If a window is found for `atMs` (`windowByPoint`): append `windowDetailLines(item, window, now)` — the exact same lines `windowTooltipHtml` appends, so a block-hover and a line-hover over the same window show matching stats.
4. If no window: stop after the usage line (still a valid, if shorter, tooltip).

### 4. Tests (`frontend/src/chart.test.ts`)

- Delete the `describe("axisTooltipHtml", ...)` block; it tests the removed
  function.
- Delete/replace the `pointTooltipHtml` tests with `seriesPointTooltipHtml`
  tests, covering: plain point (no window), point inside a window (checking
  the merged window-detail lines appear), the projected-value-past-last-point
  case, and the native-usage-label case.
- Add tests for the new `itemTooltipHtml` dispatcher: a `componentType:
  "series"` line hover, a `componentType: "markArea"` window-block hover
  (hand-built `params.data` matching the shape `chartOption()` emits), and a
  `seriesId: "notes-marker"` hover — following the existing pattern in this
  file of calling the exported pure function directly with hand-crafted
  params rather than driving real ECharts (see how `axisTooltipHtml` was
  tested).
- `windowTooltipHtml`'s existing tests are unaffected (function unchanged).

### 5. `frontend/src/components/UsageChart.vue`

No changes needed — `pinTooltip()`, `pinnedTooltipData`, and the click
handler on `chart.getZr()` all go through `axisTooltipData()` directly and
don't touch the hover formatter.

## Verification

- `corepack yarn@4.9.2 run test --run src/chart.test.ts src/components/UsageChart.test.ts`
- `corepack yarn@4.9.2 run type-check`
- Start the dev server and manually hover a line, hover a window's shaded
  background block, hover a note marker, and click to confirm the pinned
  "all entries" overlay still opens with full grouped content — per the
  CLAUDE.md instruction to verify graph edits in a real browser, not just
  unit tests.
