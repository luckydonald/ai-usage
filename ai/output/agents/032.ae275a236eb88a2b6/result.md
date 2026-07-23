Confirmed. `samples()` (history.py:196-204) applies the `metrics` filter as `MetricSampleRecord.metric_key.in_(values)` — a flat `IN` clause with no join/scoping to `account_id`. It's ANDed with the separate `accounts` filter, but if `filters.accounts` is empty (no account selected — the default/common case), the `metric_key.in_(["five-hours"])` clause alone matches **every** account's "five-hours" rows.

## Findings

**1. Types (`frontend/src/types.ts:98-124`)**
```ts
export interface Filters { services: string[]; providers: string[]; accounts: string[]; metrics: string[]; }
export interface CatalogMetric { service: string; provider: string; account_id: string; metric_key: string; metric_name: string; }
export interface FunnelMetric { key: string; name: string; }
export interface FunnelAccount { id: string; label: string; metrics: FunnelMetric[]; }
export interface FunnelProvider { provider: string; accounts: FunnelAccount[]; }
export interface FunnelBranch { service: string; providers: FunnelProvider[]; }
```
`filters.metrics` is a **flat `string[]` of bare `metric_key` values**, with no account/provider qualifier.

**2. `App.vue`**
- `serviceProviderTree` (lines 61-87): builds nested `Map`s keyed by `service → provider → account_id`, and for each account pushes into its own `metrics: FunnelAccount["metrics"]` array (line 68-72). Each account node is independent, so identical `metric_key`s across accounts each get their own chip list.
- `pruneStoredFilters` (183-192) and `metricOptions` (89-104) both dedupe/validate purely by `metric.metric_key`, with no account scoping.
- Filters sent to API via `frontend/src/api.ts:22`: `for (const value of filters.metrics) parameters.append("metric", value);` — plain `metric_key` strings, no account pairing.

**3. `FilterFunnel.vue`/`.test.ts`**: confirms 4-level tree (service→provider→account→metric leaves), test explicitly checks "Five hours"/"Seven days" appear as leaves under one account (`FilterFunnel.test.ts:17-20`). Toggle-metric emits bare `metric.key` (line 53), matched against `activeMetrics` with no account context.

**4. Backend `metric_key`** (`src/ai_usage/models.py:172`, `orm.py:56`, `history.py:166`): `metric_key` is just the metric's own key (e.g. "five-hours"), **not namespaced per account** — same string reused across all accounts of a provider.

**5. Backend filtering** (`history.py:181-209`, `api.py:157-165`): `/api/v1/series` builds one SQL statement with independent `IN` clauses per column (service/provider/account_id/metric_key), all ANDed together but **not correlated to each other**. So `metric=five-hours` alone matches every account's "five-hours" record.

**Conclusion**: Toggling "five-hours" under Account A's chip in the funnel also toggles it in `filters.metrics` globally, affecting Account B's "five-hours" series too — metric selection is **not** scoped per-account. And yes, the tree renders duplicate "Five hours"/"Seven days" leaf chips, one under each account, when two accounts share the same provider and metric_key set.