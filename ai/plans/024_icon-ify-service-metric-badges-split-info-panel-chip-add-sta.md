# Icon-ify service/metric badges, split info-panel chip, add stat icons

## Context

The dashboard (`frontend/src/` Vue app + FastAPI backend `src/ai_usage/api.py`) currently spells out
raw strings in two places that should be icons instead: the Sankey filter overlay
(`FilterSankey.vue`) shows literal service names ("claude", "codex") as chip text, and the
per-account info panels (`ServicePanels.vue`) repeat the same raw service name plus a single
combined account/parser badge. The goal is to compress this into icons with tooltips (no
information lost, just denser), consistent with the icon infrastructure already in place
(`Icon.vue` + backend-proxied Font Awesome SVGs, `SERVICE_ICONS`/`provider_icons` in
`graph.py`/`api.py`).

Confirmed via screenshot of the running app (localhost:4458) and user clarification:
- "The overlay" = the Sankey filter chips (`FilterSankey.vue`), where "claude"/"codex" literally
  appear today as icon+text chips. This becomes icon-only + tooltip.
- Metric/time-window chips ("Five hours", "Seven days", ...) in that same overlay keep their text
  label, just gain a small leading icon.
- The dot-joined ECharts legend/tooltip strings in `chart.ts`/`App.vue`'s `chartLabels` are a
  separate, canvas-rendered feature and are **out of scope** here (raw service name doesn't even
  appear there, and echarts legend can't embed real DOM icons/tooltips without much bigger work).
- Info panels (`ServicePanels.vue`): drop the raw `panel.service` text heading in favor of the
  service icon (tooltip = full name), and split the existing single account-chip into two chips:
  crawler-type (provider icon + parser label) and account-user (favicon-or-fallback + account
  label).
- Per-metric detail block gets an icon next to the metric name, and each stat line (peak/burn
  rate/etc.) gets its own icon.
- Fallback account icon (no favicon) should be tinted with the app's existing primary brand color
  (`--color-primary: #6c0de9` in `frontend/src/styles/main.scss`, same purple already used for
  active state in the Sankey overlay), not some new color.

## Backend changes

### 1. Metric icons (`src/ai_usage/graph.py` or new `src/ai_usage/metric_icons.py`)
- Add an explicit `METRIC_ICONS: dict[str, IconRef]` keyed by well-known metric keys produced by
  in-repo providers today (grep confirmed keys like `five-hours`, `seven-days*` from
  `claude_metric_key()` in `providers/claude/usage/cli/direct.py`; check other providers'
  `Metric(key=...)` call sites for their literal keys and add the common ones: session/5h, weekly,
  monthly windows).
- Add `metric_icon_for(metric_key: str, metric_name: str) -> IconRef`: explicit dict lookup first;
  on miss, keyword-heuristic on `metric_name.casefold()` — "session"/"hour" → clock, "day" →
  calendar-day, "week" → calendar-week, "month" → calendar, else a generic fallback (e.g.
  `solid/gauge`). Verify every chosen Font Awesome Free icon name actually resolves via
  `resolve_icon_svg`/`get_icon` in `icons.py` before wiring it in (some names differ between FA
  versions).
- In `api.py`'s `/api/v1/catalog` handler (~api.py:108), compute `metric_icons` as
  `{row["metric_key"]: metric_icon_for(row["metric_key"], row["metric_name"])._asdict() for row in metrics}`
  (dedup by key) and add it to the returned dict alongside `service_icons`/`provider_icons`.

### 2. Favicon proxy for account identity
- Add a route, e.g. `GET /img/favicon/{domain}`, that validates `domain` against a strict hostname
  regex, fetches the favicon server-side (e.g. from a favicon provider such as
  `https://icons.duckduckgo.com/ip3/{domain}.ico`) with a short timeout, and streams it back with a
  long `Cache-Control` — same proxy pattern as the existing FontAwesome route
  (`api.py:253-267`), so the browser never talks to a third party directly. Return 404 on any
  fetch failure/invalid domain so the frontend can fall back cleanly.
- No new persistent storage needed; an in-memory or simple disk cache keyed by domain avoids
  repeat upstream calls (follow whatever caching approach the FA icon route already relies on, if
  any, otherwise rely on the `Cache-Control` header plus browser cache).

## Frontend changes

### 3. `types.ts`
- Add `icon?: IconRef` to `SankeyMetric`.
- Add `metric_icons: Record<string, IconRef>` to `Catalog`.

### 4. `sankey.ts`
- Thread a `metricIcons: Record<string, IconRef>` param into `buildSankeyData`, and pass it to the
  metric `addNode(...)` call so metric nodes carry an icon like parser nodes already do.
- For the **service** node's `addNode` call, also pass `title: service.service` (currently no
  title is passed for service nodes) so the tooltip carries the full name once the label is
  hidden.

### 5. `Chip.vue`
- Add an `iconOnly?: boolean` prop. When true, don't render the label text (visually), but keep
  `:aria-label="label"` on the button for accessibility. `title` (tooltip) continues to show the
  full string as today.

### 6. `FilterSankey.vue`
- Pass `:icon-only="node.kind === 'service'"` to the `Chip`.
- Pass `props.metricIcons` (new prop, wired from `App.vue`'s `catalog.value.metric_icons`) through
  to `buildSankeyData`.

### 7. `Icon.vue`
- Add an optional `color?: string` prop. When set, render the icon as a `<span>` with
  `mask-image`/`-webkit-mask-image: url(...)` + `background-color: color` instead of `<img>`, so a
  single-color icon (like the fallback user icon) can be tinted via CSS. Leave the default `<img>`
  path untouched when `color` isn't passed (multi-color brand logos must stay as-is).

### 8. New small `AccountIcon` (or inline logic in `ServicePanels.vue`)
- Given an account's identity email (or account id, when it looks like an email) extract the
  domain and render `<img src="/img/favicon/{domain}">`.
- On `@error` (or no domain available), fall back to `<Icon set="solid" name="user" color="var(--color-primary)" />`.

### 9. `ServicePanels.vue`
- New props: `serviceIcons`, `providerIcons`, `metricIcons` (all `Record<string, IconRef>`), and
  enough identity data to resolve a favicon domain per account (e.g. an
  `accountIdentities: Record<string, AccountIdentity | null>` prop, or reuse `Account.identity`
  directly if the whole `accounts` array is passed instead of just label maps).
- Add `provider: string` to the internal `ServicePanel` grouping (from `first!.provider`) so the
  crawler-type icon can be looked up.
- `h2`: replace `{{ panel.service }}` text with
  `<Icon v-bind="serviceIcons[panel.service]" :title="panel.service" />` (icon-only, tooltip =
  raw service name).
- Replace the single `.account-chip` span + separate `.parser-label` paragraph with two chips:
  - Crawler-type chip: icon = `providerIcons[panel.provider]`, label = `panel.parserLabel`.
  - Account-user chip: the new favicon/fallback icon, label = `panel.accountLabel`.
- Metric detail `h3`: prepend `<Icon v-bind="metricIcons[entry.item.metric_key]" />` before
  `{{ entry.item.metric_name }}`.
- Stat lines: add one small fixed icon per row type via a local `STAT_ICONS` const (no backend
  involvement — these are UI semantics, not service data), e.g.:
  - Peak usage → `solid/gauge-high`
  - Burn rate → `solid/fire`
  - "Right on spot!" → `solid/bullseye`
  - "Hit 100% after..." → `solid/triangle-exclamation`
  - "Blocked for..." → `solid/ban`
  - "...% remaining at window end" → `solid/battery-half`
  - "Projected to land at / remaining" and "you'll hit 100% around" → `solid/chart-line`
  Verify each name resolves (same FA-name caveat as the metric icons above) before finalizing.

### 10. `App.vue`
- Pass `catalog.value.provider_icons`, `catalog.value.metric_icons`, `catalog.value.service_icons`,
  and account identity data down as new props to `<ServicePanels>` (~App.vue:383).
- Pass `metricIcons` down to `<FilterSankey>` alongside the existing `service-icons` prop
  (~App.vue:352).

## Verification
- `cd frontend && npm run type-check` (or existing lint/test script) after the Vue/TS changes.
- Run backend tests covering `/api/v1/catalog` to confirm `metric_icons` appears and each returned
  icon name actually resolves via `resolve_icon_svg`.
- Start the app (already running dev instance on `localhost:4458` was used for this
  investigation) and visually confirm in the browser:
  - Sankey overlay: service chips are icon-only with a working hover tooltip showing the full
    service name; metric chips show a small icon before their existing text.
  - Info panels: service icon-only heading with tooltip; two separate chips (crawler type,
    account user) each with an icon; metric detail heading has an icon; each stat line has its own
    icon.
  - An account whose email domain has no reachable favicon falls back to the purple user icon
    (matches `--color-primary`/Sankey active-purple).
