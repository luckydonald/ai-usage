Confirmed: `SankeyChart` exported as `install$13 as SankeyChart` from `echarts/charts` (re-exported from `types/dist/charts.d.ts`, backed by `shared.js`).

I have everything needed. Here's the report.

## Findings

**1. echarts version** — `frontend/package.json:15`: `"echarts": "^6.0.0"` (v6, tree-shaken build).

**2. SankeyChart availability** — Yes. `frontend/node_modules/echarts/types/dist/charts.d.ts:1` exports `install$13 as SankeyChart` (and `SankeySeriesOption`) from `echarts/charts`, so `import { SankeyChart } from "echarts/charts"` works today. No component currently imports `TooltipComponent`/`GraphicComponent` for a Sankey use — `TooltipComponent` is already imported/registered in `frontend/src/components/UsageChart.vue:3,16` (for the line chart), but `GraphicComponent` isn't used anywhere in `frontend/src` (`grep -rn "GraphicComponent" frontend/src` → no hits). A Sankey diagram doesn't strictly need `GraphicComponent`; `TooltipComponent` can likely be reused/shared.

**3. UsageChart.vue patterns** — Registration: `echarts.use([LineChart, GridComponent, LegendComponent, LegendScrollComponent, TooltipComponent, MarkAreaComponent, MarkLineComponent, CanvasRenderer])` (`UsageChart.vue:11-20`). Init: `chart ??= echarts.init(container.value)` then `chart.setOption(...)` (`UsageChart.vue:89-101`). Click handling is **canvas-level via zrender**, not series-level node clicks:
```js
chart.getZr().on("click", (event) => {
  void pinTooltip(event.offsetX, event.offsetY);
});
```
(`UsageChart.vue:109-111`), plus a separate `chart.on("legendselectchanged", ...)` handler (`UsageChart.vue:103-108`) that maps legend name back to a series key and emits `toggle-series`. There is no example of `chart.on('click', ...)` with `params.dataType`/`params.data` in this repo — a Sankey filter component would need to add that pattern fresh. Dark-mode theming is NOT an echarts "theme" — `chartOption()` (`frontend/src/chart.ts:325`) takes a `dark: boolean` param and inlines colors per dark/light branch (e.g. `chart.ts:437,442-444,449,457-459,466-468`); comment at `UsageChart.vue:22-26` explains why (UMD dark-theme file misbehaves under Vitest/happy-dom).

**4. Sankey type-def support** (`echarts/types/dist/echarts.d.ts`, ~line 11838-11895): `SankeyNodeItemOption` has per-node `itemStyle` (via `SankeyNodeStateOption`) and `focusNodeAdjacency?: FocusNodeAdjacency` (`'inEdges' | 'outEdges' | 'allEdges' | boolean`). `ExtraStateOption$2.emphasis.focus` is typed `DefaultEmphasisFocus | 'adjacency' | 'trajectory'` — confirming `emphasis: { focus: 'adjacency' }` is supported for highlighting connected links on hover/select.

**5. FilterFunnel sizes/contract** — `FilterFunnel.vue` = 125 lines, `FilterFunnel.test.ts` = 84 lines. Props: `tree: FunnelBranch[]`, `activeServices/activeProviders/activeAccounts/activeMetrics: string[]`, optional `serviceIcons`/`providerIcons`. Emits: `toggle-service`, `toggle-provider`, `toggle-account`, `toggle-metric` (each carrying the string id/key). A Sankey replacement should keep this exact contract to stay a drop-in swap.

**6. Vitest mock pattern** (`UsageChart.test.ts:4-23`) — mocks `echarts/core` with `vi.mock("echarts/core", () => ({ init: vi.fn(() => chart), use: vi.fn() }))`, where `chart` (via `vi.hoisted`) stubs `containPixel`, `convertFromPixel`, `dispatchAction`, `dispose`, `getZr: vi.fn(() => ({ on: vi.fn() }))`, `on`, `resize`, `setOption`. A new Sankey component would need the same shape plus asserting on `chart.on.mock.calls` for `'click'` (series-level) rather than `getZr().on`.