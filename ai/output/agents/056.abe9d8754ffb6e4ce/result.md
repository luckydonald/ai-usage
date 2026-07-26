I now have all the findings needed. Here's my report.

## Summary

This is a **Vue 3 + TypeScript web frontend** (`frontend/src/`), served by a FastAPI backend (`src/ai_usage/api.py`). It's not a native GUI toolkit (no Qt/tkinter) — it's rendered in a browser, with the "overlay" being CSS-positioned DOM elements layered atop a canvas chart (Apache ECharts). There is no separate "overlay widget"/native window; the app is a single-page dashboard.

**1. Service name rendered as text/badge**
- `frontend/src/components/Chip.vue:17-20` — generic `<button class="chip">` renders `<Icon>` + `{{ label }}`. Used both as the filter chip and as service/account/parser badges.
- `frontend/src/components/FilterSankey.vue:143-153` — `<Chip>` instances overlaid on a Sankey diagram, one per node (service/account/organization/parser/metric), `label="node.displayName"`, `icon="node.icon"`.
- Display names built in `frontend/src/sankey.ts:50-51` (`addNode(id, displayName, kind, refId, active, icon, title)`).
- `frontend/src/components/ServicePanels.vue:66` — `<h2>{{ panel.service }} <span class="account-chip">{{ panel.accountLabel }}</span></h2>`.
- Also composed as a text string (not badge) in `frontend/src/chart.ts:7-9` (`seriesDisplayName`: `${metric_name} · ${provider} · ${account}`) and `:167` (tooltip header).

**2. Time window / metric labels ("5h", "week", "session", etc.)**
- `frontend/src/time.ts:3-17` — `TimePreset` type (`"1h"|"3h"|"6h"|"12h"|"day"|"week"|"month"|"year"|"all"|"custom"`) and `presetLabels` map (e.g. `week: "7 days"`).
- Rendered in a plain `<select>`: `frontend/src/App.vue:309-310` (`<option v-for="(label, key) in presetLabels">`).
- Per-metric window labels aren't a fixed enum — they come from backend `metric_name` (e.g. "Session", "Weekly limit") rendered in `ServicePanels.vue:69` (`<h3>{{ entry.item.metric_name }}</h3>`) and in chart tooltip rows, `frontend/src/chart.ts:303` (`${row.item.metric_name}: ${row.valueLabel}`).

**3. Info panels — deprecated-name badge, crawler type, account/user info**
- `frontend/src/components/ServicePanels.vue` is the info-panel component: service name (`:66`), account chip (`:66-67`, label from `accountLabels`), "parser label" i.e. crawler/provider type (`:67`, `parserLabel` — sourced from backend `Account.parser_label`, `frontend/src/types.ts:23`), and per-metric stats (`:68-87`).
- **No "deprecated name" badge/chip exists anywhere in the codebase** — searched frontend and backend (`grep -rniE "deprecat"` across `frontend/src` and `src/ai_usage`) with zero hits. This would be new UI, not an existing feature to modify.
- Account/user identity model: `frontend/src/types.ts:1-24` (`AccountIdentity { name, email }`, `Account.identity`), populated from backend but not currently rendered in `ServicePanels.vue` (only `accountLabel`/`parserLabel` are shown there — identity name/email isn't wired into this panel yet, worth checking before assuming it's displayed).

**4. Existing icon/asset system**
- Icons are **Font Awesome Free SVGs proxied through the backend**, not bundled static assets.
- Frontend: `frontend/src/components/Icon.vue:1-21` — `<img :src="/img/icons/${pack}/${version}/${set}/${name}.svg">`, props `name/set/pack/version` (defaults `pack="fontawesome-free-pack"`, `set="brands"`, `version="latest"`).
- Type: `frontend/src/types.ts:44-49` (`IconRef { name, set, pack, version }`).
- Icon mapping per service: `src/ai_usage/graph.py:36-40` — `SERVICE_ICONS: dict[str, IconRef]` (e.g. `"claude": IconRef(set="brands", name="claude")`, `"codex": → "openai"`, `"copilot": → "github"` with a comment explaining the GitHub-as-stand-in choice).
- Per-provider icons assembled in `src/ai_usage/api.py:130-133`.
- Catalog exposes both maps to frontend: `src/ai_usage/api.py:157-158` (`service_icons`, `provider_icons`) matching `Catalog` type in `frontend/src/types.ts:51-57`.
- SVG resolution/serving: `src/ai_usage/icons.py:1-30` (`IconRef` NamedTuple, `resolve_icon_svg()` using the `fontawesome_free_pack` package) and routes `src/ai_usage/api.py:253-272` (`GET /img/icons/fontawesome-free-pack/v{version}/{set}/{name}.svg`, plus a `/latest/` redirect variant).
- Brand base colors (separate from icons) at `src/ai_usage/graph.py:26-31` (`SERVICE_BASE_COLORS`).

**5. Tooltip mechanism / GUI framework**
- Framework confirmed: **Vue 3 SFCs + SCSS**, chart rendering via **Apache ECharts** (`echarts/core`, `SankeyChart`, `CanvasRenderer`, imported in `frontend/src/components/FilterSankey.vue:1-12` and used in `frontend/src/components/UsageChart.vue`).
- Native browser `title` attribute tooltips (simplest form):
  - `frontend/src/components/Chip.vue:18` — `:title="title"` on the chip button.
  - `frontend/src/components/FilterSankey.vue:150` — `:title="node.title"`.
  - `frontend/src/components/ServicePanels.vue:67` — `:title="\`Configuration ${panel.accountId}\`"`.
  - `frontend/src/components/RelativeTime.vue:16` — `<span :title="absolute">{{ relative }}</span>` (relative-time-with-absolute-on-hover pattern), also reused inline in `frontend/src/chart.ts:128-132`.
- ECharts native hover tooltip: configured in `frontend/src/chart.ts:438` (`tooltip: {...}` option block) and built up via `frontend/src/chart.ts:230-316` (grouped hover tooltip logic, `compactWindowDetail`, per-series rows).
- A custom **pinned/modal tooltip** overlay (click-to-pin, not just hover) in `frontend/src/components/UsageChart.vue:43,52,144,152-216` — `tooltipOpen` ref, `.tooltip-overlay`/`.pinned-tooltip`/`.pinned-tooltip-content` (renders HTML via `v-html`), with a close button, used for "Usage details" (`role="dialog" aria-modal="true"`).