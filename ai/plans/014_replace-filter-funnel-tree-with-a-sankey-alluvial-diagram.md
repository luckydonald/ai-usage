# Replace filter funnel tree with a Sankey/alluvial diagram

## Context

`FilterFunnel.vue` renders the service → provider → account → metric filter hierarchy as a
hand-built tree of `Chip`s connected by CSS border-left "guide lines". The metric filter
(`Filters.metrics`) is **not** account-scoped in the actual filtering model — it's a flat list of
bare `metric_key` strings (`frontend/src/types.ts`), applied via an `IN` clause with no
correlation to account (`src/ai_usage/history.py`'s `samples()`), and `metricOptions`/
`pruneStoredFilters` in `App.vue` already dedupe/validate metrics globally by `metric_key` alone.

Because the funnel is a strict tree, when two accounts under the same provider share a
`metric_key` (e.g. two Claude orgs both exposing "five-hours"/"seven-days"), the metric chip is
duplicated once per account — misleading, since toggling either one actually toggles the same
shared filter value for both accounts.

Fix: rebuild this as an actual Sankey/alluvial diagram (echarts `SankeyChart`, already available
in the installed `echarts` v6). Sankey diagrams naturally handle convergence — a metric shared by
two accounts becomes one node with two incoming links — solving the duplication by construction
instead of by CSS/dedup hacks.

## Node identity scheme (the key design decision)

- service: `service:${service}`
- provider: `provider:${service}:${provider}` (kept per-service; two services having a
  same-named provider are still logically distinct rows, matching today's nested tree)
- account: `account:${accountId}` (globally unique real IDs)
- metric: `metric:${metric_key}` — **global**, not prefixed by provider/account. This matches how
  `filters.metrics`/`metricOptions`/`pruneStoredFilters` already treat `metric_key` as a global
  identity, and is exactly what makes shared metrics converge into one node.

## Implementation

1. **`frontend/src/sankey.ts`** (new, pure logic, parallel to `chart.ts`'s option-builder pattern):
   - `buildSankeyData(tree: FunnelBranch[], active: {services, providers, accounts, metrics}, dark: boolean): { nodes: SankeyNodeDatum[]; links: SankeyLinkDatum[] }`
   - Walks `tree` once, deduping nodes via `Map`s keyed by the id scheme above (metric map keyed
     by `metric_key` only, regardless of which account/provider it's reached from), emitting one
     link per parent→child edge (so a shared metric gets multiple incoming links).
   - Each node carries display `name` (service/provider raw string, account `label`, metric
     `name`) plus non-rendered `kind: "service"|"provider"|"account"|"metric"` and `refId` (the
     raw id to emit, e.g. the bare `accountId` or `metric_key`) — needed because Sankey `name` is
     just display text and can collide across kinds.
   - Active/inactive color via `itemStyle.color` (reuse existing `--color-primary` active color
     and light/dark inactive surface colors, mirroring `chart.ts`'s explicit dark-branch
     constants — no `echarts/theme/dark`, per this repo's established reasoning about Vitest/
     happy-dom UMD incompatibility).
2. **`frontend/src/sankey.test.ts`** (new): pure unit tests, no Vue/echarts — two accounts sharing
   `metric_key: "five-hours"` produce exactly one metric node and two links into it; empty tree;
   active-state coloring.
3. **`frontend/src/components/FilterSankey.vue`** (new, replaces `FilterFunnel.vue`):
   - Same props/emits contract as `FilterFunnel.vue` (`tree`, `activeServices/Providers/Accounts/
     Metrics`) plus a new `dark: boolean` prop (old component never needed it).
   - Mirrors `UsageChart.vue`'s echarts-in-Vue pattern: `echarts.use([SankeyChart,
     TooltipComponent, CanvasRenderer])`, `chart ??= echarts.init(container.value)`, `setOption`
     on mount and on prop change (`watch(..., { deep: true })`), dispose in `onBeforeUnmount`.
   - `chart.setOption(sankeyOption(...))`: series type `'sankey'`, `emphasis: { focus:
     'adjacency' }` (highlights connected links on hover), `orient: 'horizontal'`.
   - New click pattern (first in this codebase): `chart.on('click', (params) => { if
     (params.dataType !== 'node') return; const { kind, refId } = params.data; emit(`toggle-
     ${kind}`, refId); })`.
   - **Known trade-off**: `serviceIcons`/`providerIcons` (real `Icon.vue`-rendered icons, used
     today) are dropped from node labels in this first version — echarts canvas labels can't host
     a Vue `Icon` component, and faking it via image-URL rich-text is not worth the complexity
     here. Nodes render as plain text labels. Flagging this explicitly since it's a visible (if
     minor) regression from today's chip icons.
4. **`frontend/src/components/FilterSankey.test.ts`** (new): copy `UsageChart.test.ts`'s
   `vi.mock("echarts/core", ...)` shape; assert `setOption` receives expected nodes/links for a
   fixture tree; simulate a node click via the mocked `chart.on.mock.calls` entry and assert the
   right `toggle-*` event is emitted with the right raw id (including the shared-metric case:
   clicking the one shared metric node emits `toggle-metric` with that `metric_key`).
5. **`frontend/src/App.vue`**: swap `import FilterFunnel from "./components/FilterFunnel.vue"` →
   `FilterSankey`, same template block/props/emits, add `:dark="dark"`. No changes to
   `serviceProviderTree`, `metricOptions`, or `pruneStoredFilters` — the tree shape feeding this
   component is unchanged.
6. **Cleanup**: delete `frontend/src/components/FilterFunnel.vue` and `FilterFunnel.test.ts`
   (only consumer was `App.vue`). Leave `Chip.vue`/`Icon.vue` in place — untouched, out of scope.

## Build order

1. `sankey.ts` + `sankey.test.ts` (fastest feedback, no Vue/echarts mocking needed).
2. `FilterSankey.vue` using `sankey.ts`.
3. `FilterSankey.test.ts`.
4. Wire into `App.vue`; run full frontend test suite + `vue-tsc --noEmit`.
5. Real-browser check (seeded backend, as done for prior chart work) in both light and dark mode,
   confirming: shared metric across two accounts renders as one converging node, clicking any
   node toggles the right filter and re-loads data, hover highlights connected links.
6. Delete `FilterFunnel.vue`/`FilterFunnel.test.ts`.

## Verification

- `yarn vitest run` (new `sankey.test.ts`, `FilterSankey.test.ts`, full suite for regressions).
- `yarn vue-tsc --noEmit`.
- `corepack yarn@4.9.2 build` + real-Chromium check against a seeded backend (two accounts under
  one provider sharing a metric_key) to confirm the visual convergence and click-to-filter
  behavior, light and dark mode.
