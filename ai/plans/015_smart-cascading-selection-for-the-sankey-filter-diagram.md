# Smart cascading selection for the Sankey filter diagram

## Context

The Sankey filter diagram (`FilterSankey.vue`) lets you click any node (service/provider/
account/metric) to toggle it in `Filters`, but today each click only touches its own dimension's
array — no relationship between columns. That causes two real problems the user hit in practice:

1. **Deselected links are basically invisible** (`sankey.ts`'s inactive-link opacity is `0.15`),
   so the "background" structure of the diagram disappears entirely once anything is filtered.
2. **Clicking one node doesn't keep the rest of the diagram meaningfully connected/visible.**
   E.g. selecting a provider should imply its service and its accounts/metrics are part of the
   same story; deselecting the last active account under a provider should retire that provider
   too (and cascade further); enabling a metric that nothing currently active would actually
   display should smartly pull in just enough upstream nodes to make it visible — without
   force-enabling metrics that aren't needed when something already shows.

Additionally, the user wants to flip the *default* semantics: **empty filter lists currently mean
"show everything" (unrestricted)**. That makes "temporarily deselect everything, then reselect the
other one" ambiguous/order-dependent (the empty state acts as "select only the next thing clicked",
not literally "nothing"). The new model: **filters always hold an explicit list.** The default
(first-ever load) populates all four lists with every catalog value (visually identical to today's
default), but from then on an empty list literally means "nothing", shows a warning, and does not
silently fall back to "show all".

## Confirmed design decisions (from user Q&A)

- **Leftward "ensure ancestor active" is just a plain, unconditional union-add.** Under the
  always-explicit model there's no more "empty list = unrestricted" state to accidentally narrow,
  so this is no longer conditional — it was only conditional under the old semantics.
- **Service-level cascade (leftmost column) force-enables every reachable provider, account, AND
  metric unconditionally** — no smart per-account metric check at this level (user's explicit
  choice: "Always force-enable all metrics").
- **Provider- and account-level cascades still use the smart metric rule**: for each account
  reached, only union-add *all* of that account's metric keys into `filters.metrics` if none of
  its own metric keys are already in there (i.e. only when it would otherwise show nothing);
  leave `filters.metrics` untouched if the account can already display something.
- **Metric-level enable**: if any account that has this `metric_key` is already active, do
  nothing else. Otherwise, union-add *every* account with this metric key, plus their providers
  and services (ancestors), so the metric is guaranteed to actually display.
- **Disable is one general recursive rule**: after removing a value, repeatedly scan all four
  (now always-explicit) filter lists; drop any listed value that has zero remaining active
  neighbors in its immediately adjacent column(s) (service↔provider, provider↔account,
  account↔metric — metric checks are tree-wide, since metric nodes are globally deduped by
  `metric_key` across services/providers). Repeat until a full pass makes no changes (fixpoint).
  Metrics/accounts/providers/services all check on the *now-explicit* adjacent list — an empty
  adjacent list means zero neighbors are active, so a total-empty column correctly ripples out and
  clears everything connected to it, matching "deselect everything → warning".

## Implementation

### 1. New file: `frontend/src/filterCascade.ts` (pure logic, parallel to `sankey.ts`/`time.ts`)

Builds a small lookup index once per call from the existing `FunnelBranch[]` tree (service→
providers, provider→services + provider→accounts, account→provider/service/metric-keys, metric→
accounts — all keyed the same way `sankey.ts` already keys nodes, i.e. provider/metric identity is
name-only/global, not scoped by branch), then exposes:

- `defaultFilters(tree: FunnelBranch[]): Filters` — every service/provider/account/metric_key in
  the tree, fully populated (the new "show everything" representation).
- `toggleService(tree, filters, service): Filters`
- `toggleProvider(tree, filters, provider): Filters`
- `toggleAccount(tree, filters, accountId): Filters`
- `toggleMetric(tree, filters, metricKey): Filters`

Each `toggleX` checks current membership to pick enable vs. disable, and returns a **new** full
`Filters` object (all four arrays) — never mutates its input, easy to test in isolation. Disable
delegates to a shared `pruneOrphans(index, filters)` fixpoint helper; enable delegates to small
per-level helpers (`smartEnableAccountMetrics`, ancestor union-adds) as described above.

### 2. `frontend/src/filterCascade.test.ts` (new)

Exhaustive pure-function coverage, no Vue/echarts involved:
- `defaultFilters` populates all four dimensions from a fixture tree.
- Service enable force-enables all descendant providers/accounts/metrics unconditionally.
- Provider enable: ensures its service (union), enables all its accounts, and only smart-enables
  an account's metrics when that account has none already active.
- Account enable: ensures provider+service ancestors, applies the same smart metric rule.
- Metric enable: no-op beyond adding the metric key when an already-active account already has it;
  otherwise unions in every account with that key plus their ancestors — including the
  cross-service shared-metric case (metric reachable via two different services) to confirm it
  doesn't over-enable unrelated accounts that don't have this key.
- Disable: reproduces the user's own worked example (disabling an account orphans its provider,
  which — if it was the service's last active provider — orphans the service too; any metric whose
  only active account was this one is dropped too), plus the metric-column mirror (disabling the
  last metric of an account can orphan that account, cascading further left), plus confirming a
  metric shared across two *different* services is **not** orphaned while any one connected
  account elsewhere remains active.

### 3. `frontend/src/sankey.ts`

Bump the inactive-link opacity in `linkStyle` from `0.15` to a clearly-visible-but-secondary value
(e.g. `0.35`) so deselected connections stay visible as background structure.

### 4. `frontend/src/App.vue`

- `loadStoredFilters()` returns `Filters | null` (`null` = no localStorage entry at all, i.e.
  never customized) instead of an empty-arrays `Filters`.
- In `onMounted`, after `catalog.value = await fetchCatalog()` (so `serviceProviderTree` is
  available): if the stored filters were `null`, initialize `filters` via
  `defaultFilters(serviceProviderTree.value)` (fully populated); otherwise keep the loaded value
  and run the existing `pruneStoredFilters()` (unchanged — still just drops now-invalid stale
  entries, doesn't need to handle catalog-growth auto-extension since the catalog is only fetched
  once per page load today).
- Replace the four inline `@toggle-*` handlers in the template: instead of
  `filters.services = toggleFilter(filters.services, item)`, call
  `filterCascade.toggleService(serviceProviderTree.value, filters, item)` (etc. per dimension) and
  assign all four returned arrays onto the reactive `filters` object, then `load()`. Delete the
  now-unused standalone `toggleFilter` helper.
- Simplify the `services`/`providers`/`accounts`/`metricOptions` computeds: they're only used for
  the `v-if` gate that decides whether to render `FilterSankey` at all (`services.length > 1 ||
  ...`), and their current `!filters.X.length || ...` narrowing logic is stale leftover from the
  old flat-chip-list UI (the Sankey diagram always shows the full tree already, per
  `serviceProviderTree`'s own comment). Simplify all four to plain unfiltered catalog cardinality
  checks.
- Add a `hasEmptyFilterDimension` computed (`!filters.services.length || !filters.providers.length
  || !filters.accounts.length || !filters.metrics.length`). Guard the top of `performLoad`: if
  true, set `series.value = []` and return without calling `fetchSeries` (avoids sending an
  effectively-empty-but-ambiguous request — an omitted query param today means "unrestricted" on
  the backend, which would be wrong here). In the template, show a distinct warning message (e.g.
  "Nothing selected in at least one filter — deselect fewer things to see data.") ahead of the
  existing "No usage samples in this range." state.

No backend changes needed — `api.ts`'s `fetchSeries` keeps sending whatever's in each array
unchanged; a fully-populated array is functionally equivalent to today's "omit the param" case.

### 5. `tests/test_e2e_filters.py` (existing Playwright tests — behavior actually changes)

`test_service_filter_selection_survives_a_page_reload` currently clicks an untouched "codex" chip
expecting it to *narrow* to `services: ["codex"]`. Under the new default-fully-populated model, a
fresh chip is **already active**, so that same click now **disables** codex, leaving the other
service(s) active instead. Rewrite this test to click a service chip and assert the disable
outcome (services list becomes "all except that one"), persisted across reload and reflected in
the next `/api/v1/series` request. `test_stale_filter_from_an_older_catalog_is_pruned_instead_of_
hiding_everything` seeds an explicit (non-null) localStorage value directly, so it bypasses the new
default-population path and should need little to no change — verify it still passes as-is.

## Verification

- `yarn vitest run` (new `filterCascade.test.ts` plus full regression pass).
- `yarn vue-tsc --noEmit`.
- `uv run pytest tests/test_e2e_filters.py` (after `corepack yarn@4.9.2 build`) — updated + passing.
- Real-browser check (seeded backend, light + dark): confirm default view shows everything with
  every chip active; disabling an account cascades to orphan its provider/service/metric chips
  when they lose their last connection; enabling a metric with nothing feeding it pulls in an
  account+ancestors; deselecting every chip in one column shows the new warning instead of a blank
  chart.
