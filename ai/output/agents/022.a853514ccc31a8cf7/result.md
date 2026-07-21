No `icon` attribute exists anywhere in the codebase (backend or frontend). Here is the precise report.

## Answer: chip generation is fully dynamic from the catalog API response — no hardcoded display-name mapping in Vue

### 1. `frontend/src/App.vue`

- `services` computed (`frontend/src/App.vue:30`): `[...new Set(catalog.value.metrics.map((metric) => metric.service))]`
- `providers` computed (`frontend/src/App.vue:31`): same pattern over `metric.provider`, filtered by selected services
- `accounts` computed (`frontend/src/App.vue:32`): filters `catalog.value.accounts` by service/provider
- `metricOptions` computed (`frontend/src/App.vue:33-48`): dedupes by `metric.metric_key`, using `metric.metric_name` as display text (this one *is* a name, not a raw key)
- Chip templates: `frontend/src/App.vue:221-230` (Services) renders `{{ item }}` directly — the raw `service` string from the catalog, e.g. `"claude"`, `"codex"`. `frontend/src/App.vue:231-240` (Providers) renders `{{ item }}` directly — the raw `provider`/`key` string, e.g. `"web"`, `"statusline"`, `"app-server"`. Accounts (`241-250`) use `accountLabel()` (`App.vue:54-57`, a helper combining `account.name` + identity), and Metrics (`251-260`) use `metric_name`.

So: **service and provider chips are literally the raw backend string values, with zero display-name/label mapping in Vue.** The only "mapping" logic in App.vue is for accounts (name + identity) and metrics (uses the already-resolved `metric_name` string from the backend).

### 2. `frontend/src/api.ts` / `frontend/src/types.ts`

- `fetchCatalog()` at `frontend/src/api.ts:9-11` — plain `GET /api/v1/catalog`, no transformation.
- `CatalogMetric` (`frontend/src/types.ts:25-31`): `{ service, provider, account_id, metric_key, metric_name }` — no `display_name` field.
- `Account` (`frontend/src/types.ts:13-23`): `{ id, service, provider, name, enabled, colors, identity, subscription, group_id }` — no `display_name`/`icon` field either.
- `Catalog` (`frontend/src/types.ts:33-37`): `{ accounts, metrics, exhausted_color }`.

**The catalog response contains only raw `service`/`provider` keys, never `display_name`.**

### 3. `src/ai_usage/api.py` catalog endpoint

`src/ai_usage/api.py:99-118`:
```python
@app.get("/api/v1/catalog")
async def catalog() -> dict[str, Any]:
    accounts = state.config.list_accounts(False)
    async with state.database.sessions() as session:
        rows = await session.execute(
            select(
                MetricSampleRecord.service,
                MetricSampleRecord.provider,
                MetricSampleRecord.account_id,
                MetricSampleRecord.metric_key,
                MetricSampleRecord.metric_name,
            ).distinct()
        )
        metrics = [dict(row._mapping) for row in rows]
    return {
        "accounts": [account.model_dump(mode="json") for account in accounts],
        "metrics": metrics,
        "exhausted_color": "#6b7280",
    }
```
The `service`/`provider` strings come straight from the persisted `MetricSampleRecord` DB rows (i.e. whatever the provider wrote at fetch time, `service`/`key` class attrs — see below). `Provider.display_name` (`src/ai_usage/providers/base.py:36`) **exists as a class attribute but is never read by `api.py` and is never included in the catalog/series/notes/latest responses.** It's currently used only internally for login UX strings (e.g. `capture_cookies_via_webview(self.login_url, self.display_name)` in `claude.py:246`, `codex.py:202`).

### 4. Distinct `service` values (grep `service = "..."` across `src/ai_usage/providers/*.py`)

- `"claude"` — `claude.py:230`, `claude.py:409`
- `"codex"` — `codex.py:187`, `codex.py:348`, `codex.py:431`
- `"copilot"` — `copilot.py:32`, `web.py:62`

So the exact brand-identifier set currently in code is **`claude`, `codex`, `copilot`** (3 brands, 6 provider classes). Note: `graph.py`'s `SERVICE_BASE_COLORS` (see below) already anticipates `gemini`, `perplexity`, `cursor` as future services, but no provider classes for those exist yet.

Each provider class also defines a `key` (the "provider" chip value, e.g. `"web"`, `"statusline"`, `"cli-usage"`, `"app-server"`, `"cli-status"`, `"github-api"`, `"entitlements"`) and a `display_name` (human string like `"Claude private web API"`), but only `service`/`key` propagate into the DB/API — `display_name` does not.

### 5. Backend `Provider` base class + color precedent (`src/ai_usage/providers/base.py:33-40`)

`Provider` only declares `service`, `key`, `display_name`, `experimental`, `configuration_fields`, `login_url`, `login_hint` — **no `color`/`icon`/`brand` attribute.**

The color-mapping precedent lives entirely **backend-side in `src/ai_usage/graph.py`**, not frontend:
- `SERVICE_BASE_COLORS: dict[str, str]` at `graph.py:26-32` — a hardcoded `service -> hex` lookup dict (not a `Provider` class attribute).
- `brand_color_variant()` (`graph.py:56-66`) and `generated_color()` (`graph.py:69-76`) derive deterministic per-account/metric lightness variants of that base hue via `colorsys`, falling back to a generic `PALETTE` (`graph.py:11-20`) when the service isn't in `SERVICE_BASE_COLORS`.
- This computed color is injected into `GraphSeries.color` inside `build_series()` (`graph.py:104-131`), which is what backs `frontend/src/types.ts`'s `GraphSeries.color` (`types.ts:76`) — i.e., colors reach the frontend as a plain computed field on each series object from `/api/v1/series`, not as a frontend lookup table. (Also note `Account.colors: dict[str,str]` in `src/ai_usage/models.py:131` lets per-account colors be explicitly configured, overriding the generated ones — see `api.py:152-156`.)

**Important correction to your recollection:** there is no `generated_color` (or any color/icon logic) in `frontend/src/chart.ts` — that file only references `` `Service: ${item.service}` `` (`chart.ts:112`) for tooltips, using the raw string. The `generated_color`/hue-based brand-color function you were thinking of is in **`src/ai_usage/graph.py` (backend Python)**, keyed by a hardcoded `SERVICE_BASE_COLORS` dict, not a `Provider` class attribute and not frontend code.

## Bottom line / recommendation basis

- Chips are **100% dynamic from the catalog API** — Vue does zero display-name translation for service/provider chips (only account labels and metric names, which are already backend-resolved strings).
- `display_name` exists on `Provider` (`base.py:36`) but is **not wired into any API response** today.
- The one existing precedent for "service -> visual property" mapping (color) is done **backend-side**, as a hardcoded dict (`graph.py:26-32`) keyed by the `service` string, with the result baked into the `series`/`color` field sent to the frontend — the frontend never does its own service->color (or service->icon) lookup.

Given that precedent, wiring brand icons in as a backend-side mapping (either a new `Provider.icon`/`brand` class constant analogous to `display_name`, or a `SERVICE_ICON_URLS`-style dict analogous to `SERVICE_BASE_COLORS` in `graph.py`) propagated through the catalog API (e.g. as a new `icon_url`/`icon` field per metric/service in the `/api/v1/catalog` response) would match the codebase's existing architecture pattern — not a frontend-only lookup table.