Now I have everything needed to write a concrete plan.

## Implementation Plan: FilterFunnel → Sankey Filter Selector

### Node-id / dedup scheme (the critical decision)

`Filters.metrics` (`frontend/src/types.ts:98-103`) is a bare `string[]` of `metric_key`, and both `metricOptions` (`App.vue:89-104`) and `pruneStoredFilters` (`App.vue:183-192`) already dedup/validate metrics **globally by `metric_key` alone**, with no provider scoping anywhere in the actual filter model. So the Sankey must match that semantics exactly, not invent a finer-grained id:

- service node id: `service:${service}`
- provider node id: `provider:${service}:${provider}` (providers of the same name under different services are logically distinct rows in the tree already, since `FunnelBranch.providers` is nested under service — keep them separate per branch to mirror existing per-service provider chips)
- account node id: `account:${accountId}` (globally unique, comes from real account IDs)
- metric node id: `metric:${metric_key}` **global**, deliberately not prefixed by provider/account — this is what makes two accounts sharing a `metric_key` converge into one Sankey node, and it stays consistent with `filters.metrics`/`metricOptions`/`pruneStoredFilters`, which already treat `metric_key` as a global identity. (If two providers ever need semantically distinct "five-hours" metrics, that already breaks today's filter model — out of scope for this component.)

### New file: `frontend/src/sankey.ts` (pure, parallel to `chart.ts`)

```ts
export interface SankeyNodeDatum { name: string; itemStyle?: { color: string }; label?: {...}; kind: "service"|"provider"|"account"|"metric"; refId: string }
export interface SankeyLinkDatum { source: string; target: string; value: number; lineStyle?: {...} }

export function buildSankeyData(
  tree: FunnelBranch[],
  active: { services: string[]; providers: string[]; accounts: string[]; metrics: string[] },
  dark: boolean,
): { nodes: SankeyNodeDatum[]; links: SankeyLinkDatum[] }
```

Walk `tree` once, using `Map`s keyed by the id scheme above to dedupe nodes (metric map keyed by `metric_key` only) while still creating one link per (account→metric) edge even when the metric node is shared. Each node carries `label.formatter`/`name` = the human label (service/provider raw string, account `label`, metric `name`) plus a stashed `kind`+`refId` (echarts allows unknown extra fields on data items — used by the click handler to know which emit to fire and what raw id to send, since Sankey node `name` must be display text and can collide across kinds e.g. two providers both called the same string as a metric key). Active/inactive colors: reuse `--color-primary` (`#6c0de9`) / light `#f4f2fb`, dark `#241a3d` (mirror `chart.ts`'s existing dark-branch constants) applied via `itemStyle.color`; inactive links get lower opacity via `lineStyle.opacity`.

### New file: `frontend/src/sankey.test.ts`

Pure unit tests, no Vue/echarts: given a small `FunnelBranch[]` with two accounts sharing `metric_key: "five-hours"`, assert exactly one node with `refId: "metric:five-hours"` and two links targeting it. Also test empty tree, and active-state coloring.

### New file: `frontend/src/components/FilterSankey.vue`

- Same props/emits contract as `FilterFunnel.vue` (`tree`, `activeServices/Providers/Accounts/Metrics`, `serviceIcons?`/`providerIcons?` — icons can be dropped from v1 since Sankey labels are plain text; note this as a minor visual regression, or fold icon into label text later).
- Mirrors `UsageChart.vue` structure: `echarts.use([SankeyChart, TooltipComponent, CanvasRenderer])`, `chart ??= echarts.init(container.value)`, `render()`/`resize()`/`onBeforeUnmount` dispose — copy the pattern, not `LineChart`/legend/grid components (Sankey needs no grid/legend).
- `chart.setOption(sankeyOption(...))` where `sankeyOption` builds the full echarts option from `buildSankeyData(...)`, series type `'sankey'`, `emphasis: { focus: 'adjacency' }`, `nodeAlign: 'justify'`, orient `'horizontal'`.
- On mount, register `chart.on('click', (params) => { if (params.dataType !== 'node') return; const { kind, refId } = params.data; emit(`toggle-${kind}`, rawId(refId)) })` — new pattern in this codebase, first series-click listener.
- `watch` on all props (deep) → `render(false)` like `UsageChart.vue`.

### `frontend/src/components/FilterSankey.test.ts`

Copy `UsageChart.test.ts`'s `vi.mock("echarts/core", ...)` shape (`init`, `use`, `setOption`, `on`, `dispose`, `resize`). Assert `setOption` called with nodes/links matching a fixture tree; simulate `chart.on.mock.calls.find(([name]) => name === 'click')[1]({ dataType: 'node', data: { kind: 'metric', refId: 'metric:five-hours' } })` and assert `wrapper.emitted('toggle-metric')` equals `[["five-hours"]]`.

### `App.vue` change

Only swap the import/tag: `import FilterFunnel from "./components/FilterFunnel.vue"` → `FilterSankey`, same template block (lines 293-306) — no prop/emit changes needed since contract is preserved. Pass `:dark="dark"` additionally (new prop FilterFunnel never needed).

### Cleanup

- Delete `frontend/src/components/FilterFunnel.vue` and `FilterFunnel.test.ts` outright (no reason to keep dead code once `App.vue` no longer references it — grep confirms `FilterFunnel` is only imported in `App.vue`).
- `Chip.vue` stays: only used by `FilterFunnel.vue` today per current grep, but confirm no other consumer before deleting anything else — it's fully decoupled from this change either way (Sankey renders its own canvas nodes), so leave `Chip.vue` untouched/unremoved regardless, since removing it is out of scope and risks breaking something not investigated here.

### Build order
1. `frontend/src/sankey.ts` + `sankey.test.ts` (pure logic, fastest feedback).
2. `frontend/src/components/FilterSankey.vue` (visual, using `sankey.ts`).
3. `frontend/src/components/FilterSankey.test.ts`.
4. Wire into `App.vue`, run full `frontend` test suite + manual visual check (light/dark).
5. Delete `FilterFunnel.vue`/`.test.ts`.

### Critical Files for Implementation
- /home/user/git/luckydonald/ai-usage/frontend/src/sankey.ts (new)
- /home/user/git/luckydonald/ai-usage/frontend/src/components/FilterSankey.vue (new)
- /home/user/git/luckydonald/ai-usage/frontend/src/App.vue
- /home/user/git/luckydonald/ai-usage/frontend/src/types.ts
- /home/user/git/luckydonald/ai-usage/frontend/src/components/UsageChart.vue (pattern reference)