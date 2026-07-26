---
name: project_ai_usage_icon_infrastructure
description: "ai-usage dashboard's icon/badge system after the icon-ify-dashboard series of changes — where icons live, how tooltips are structured"
metadata: 
  node_type: memory
  type: project
  originSessionId: c77b952d-3d3d-4f06-9630-bdd4829adc23
  modified: 2026-07-26T22:31:00.181Z
---

Across several commits (`dcd2982`, `d8e2186`, `f46cac3`, `d4bc3fc`, `866e2f2` on branch `mane`), the ai-usage Vue dashboard grew a full icon system replacing raw service-name text with icons/badges. Key pieces, for picking up related work later:

- **Backend** (`src/ai_usage/graph.py`, `api.py`): `SERVICE_ICONS` (per-service brand icon), `METRIC_ICONS`/`metric_icon_for()` (explicit metric_key → icon map with a keyword-heuristic fallback on `metric_name`, since `metric_key` is a free-form string minted per-provider). `/api/v1/catalog` exposes `service_icons`, `provider_icons`, `metric_icons`. New `/img/favicon/{domain}` route proxies account-identity favicons server-side (mirrors the existing FontAwesome-icon proxy pattern) — never fetch third-party favicons directly from the browser.
- **`frontend/src/components/Icon.vue`**: renders FontAwesome SVGs proxied from the backend. Gained an optional `color` prop — when set, renders via CSS `mask-image` instead of `<img>` so single-color icons (e.g. fallback user icon) can be tinted with `var(--color-primary)`.
- **`frontend/src/sankey.ts`**: `stripServicePrefix(service, label)` — strips a redundant leading service-name match (e.g. "Claude " off "Claude status line with /usage fallback") from configuration/parser labels, since the service already has its own icon/badge shown alongside. Used in `sankey.ts` itself, `ServicePanels.vue`, and `App.vue`'s `chartLabels`.
- **`frontend/src/components/Badge.vue`**: new small dumb component, a colored pill (`label`, optional `color`) — the "real component" replacement for what used to be hand-built `<span style="...">` HTML strings.
- **Chart tooltip** (`frontend/src/chart.ts`): `axisTooltipData()` is the pure-data builder (`AxisTooltipData`/`TooltipGroup`/`TooltipMetricRow`, no markup) shared by both tooltip surfaces. `axisTooltipHtml()` wraps it into an HTML string — kept *only* because ECharts' native hover tooltip manages its own floating DOM node and its `formatter` can only set innerHTML, not mount Vue. `UsageChart.vue`'s pinned/click tooltip (a real Vue dialog) calls `axisTooltipData()` directly and renders with `Icon`/`Badge` components — see [[feedback_vue_no_raw_html_strings]].

**Where things are shown, briefly:**
- Sankey overlay (`FilterSankey.vue`): service chips = icon+text (reverted from an earlier icon-only attempt per user feedback — toggle chips should keep the visible name). Metric chips = icon+text. Configuration/parser chips = deduped label via `stripServicePrefix`.
- Info panels (`ServicePanels.vue`): heading = service name text + icon *after* it (not icon-only). Per-metric heading = metric name text + icon after. Crawler-type/account-user badges + per-stat-line icons (peak/burn-rate/etc.) added earlier in the series.
- Chart hover/click tooltip: service icon + color-matched badges (account/org/config/provider, colored with the series' own graph color, deduped when config label already equals the raw provider key) instead of a "·"-joined text line; each metric line gets a leading metric icon.

Dev instance for visual verification runs via `ai-usage up` (local process, port 4458 in this environment); frontend is a static build served by the backend (`npm run build` in `frontend/`, then just reload the browser — no backend restart needed unless *backend* code changed, in which case the running process must be restarted to pick it up).
