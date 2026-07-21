# Brand icons, notice/promo polish, and relative-time display

## Context
Follow-up round of dashboard polish, bundled into one plan across six areas. All findings below were verified against the real code and the real `fontawesome-free-pack` package (installed in isolated scratch venvs, actual constants enumerated — not guessed), including two rounds of correction after the first pass: the originally-named `fontawesomefree` pip package turned out to have no Claude/OpenAI/Copilot icons at all; the replacement `fontawesome-free-pack` has Claude and OpenAI but genuinely no Copilot icon at any version (confirmed by enumerating all 2160 icon constants) — resolved by using GitHub's mark as a stand-in for Copilot, per your call.

## Key findings from research
- **Chips are 100% dynamic** — `frontend/src/App.vue`'s filter chip groups render raw `service`/`provider` strings straight from `/api/v1/catalog`, no Vue-side display-name mapping. The existing "service → visual property" precedent (color) is backend-side: `src/ai_usage/graph.py`'s `SERVICE_BASE_COLORS` dict, baked into `GraphSeries.color` before it reaches the frontend.
- **`fontawesome-free-pack` ships no on-disk SVG files** — it's a compiled Rust extension (PyO3/maturin). Icons come from `get_icon(f"{family}/{slug}")` at runtime, returning an object with `.svg` (string). Verified: `brands/claude` ✅, `brands/openai` ✅, `brands/github` ✅, `brands/copilot` / `brands/github-copilot` / `brands/microsoft-copilot` ❌ (all missing, exhaustively checked — no Copilot icon exists upstream in Font Awesome Free, at any version). Provider-icon candidates also verified directly: `solid/globe` ✅, `solid/gauge` ✅, `solid/terminal` ✅, `solid/server` ✅, `solid/key` ✅ (`solid/square-terminal` ❌, dropped).
- `src/ai_usage/api.py` has **no `APIRouter`** — every route is a plain `@app.get(...)` inside `create_app()`. A catch-all `@app.get("/{path:path}")` SPA-fallback route (`api.py:223`, only when the frontend dist exists) will **shadow any route declared after it** — new routes must go above that block. No existing `Cache-Control`/`RedirectResponse` pattern to copy; introducing fresh.
- Notes/promo text **already contains literal markdown** (`**bold**`, confirmed via the GrowthBook banner's pinned test fixture) and is rendered completely raw today. No markdown library or HTML sanitizer exists in the frontend yet.
- ECharts tooltip has `confine: true` (repositions to stay in-bounds) but no width/wrap control — there's a dedicated `tooltip.extraCssText` option for exactly this, unused so far.
- `ServicePanels.vue` doesn't build its own date strings — it dumps `windowTooltipHtml(...)`'s HTML via `v-html`. That function (and its `windowDetailLines` helper) is called from **nowhere else** — safe to change its date rendering without touching the hover tooltip (which has its own separate `compactWindowDetail`).
- `frontend/src/time.ts`'s `formatDuration(ms)` already handles signed durations (`"2h 32m"`, `"-3d 4h"`, `"<1m"`) — reusable as the basis for a relative-time helper.

## Icon addressing — a real structure, not bare strings
Per your note ("pack, version, set, name should be defined properly... so others can be used in the future"), icons are addressed with four dimensions everywhere (backend constants, API payloads, frontend props) — not just an icon name:

```python
# src/ai_usage/icons.py (new)
class IconRef(NamedTuple):
    pack: str = "fontawesome-free-pack"
    version: str = "latest"
    set: Literal["brands", "solid", "regular"] = "brands"
    name: str
```
Serializes to `{pack, version, set, name}` in API responses. The frontend `<Icon>` component's props are exactly these four (`source`/`version`/`family`/`icon`), already designed this way from the first draft of this plan — just renaming the default `source` value.

## Cluster 1 — Backend icon-serving endpoint
- Add `fontawesome-free-pack` to `pyproject.toml` dependencies.
- New `src/ai_usage/icons.py`: the `IconRef` type above, plus a small resolver wrapping `fontawesome_free_pack.get_icon(f"{set}/{name}")`.
- New routes in `src/ai_usage/api.py`, inserted **above** the `if paths.frontend.exists():` catch-all block (≈ line 217):
  - `GET /img/icons/fontawesome-free-pack/v{version}/{set}/{name}.svg` — validate `set` ∈ `{brands, solid, regular}`; validate `{version}` matches the installed `importlib.metadata.version("fontawesome-free-pack")` (we can only serve the one version actually installed; mismatch → 404); resolve via `get_icon`; `None` → 404; otherwise `Response(content=result.svg, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=31536000, immutable"})`.
  - `GET /img/icons/fontawesome-free-pack/latest/{set}/{name}.svg` — `RedirectResponse(url=f"/img/icons/fontawesome-free-pack/v{version}/{set}/{name}.svg", status_code=307, headers={"Cache-Control": "public, max-age=86400"})`.
  - Add `RedirectResponse`/`Response` to the existing `fastapi.responses` import.
- Tests in `tests/test_api.py`: known-good icon 200 + `image/svg+xml` + immutable cache header; unknown icon 404; `/latest/...` 307s to the versioned URL with the ~1-day cache header; wrong version in a versioned path 404s.

## Cluster 2 — Frontend `<Icon>` component
- `frontend/src/components/Icon.vue`: props `icon` (required, = `name`), `source = "fontawesome-free-pack"`, `family = "brands"` (= `set`), `version = "latest"`. Renders `<img :src="\`/img/icons/${source}/${version}/${family}/${icon}.svg\`" :alt="icon" class="icon" />`.
- Wrap in a small rounded/padded chip background (reuse `.chip`/`.account-chip` pill styling) so single-color brand marks stay visible against a same-toned background in dark mode.

## Cluster 3 — Icons on both service AND provider chips
**Service (brand) icons** — `src/ai_usage/graph.py`, next to `SERVICE_BASE_COLORS`:
```python
SERVICE_ICONS: dict[str, IconRef] = {
    "claude": IconRef(set="brands", name="claude"),
    "codex": IconRef(set="brands", name="openai"),   # per your ~~codex~~ → show OpenAI's mark
    "copilot": IconRef(set="brands", name="github"),  # no Copilot icon exists upstream; GitHub mark as stand-in, per your call
}
```

**Provider (per-provider-key) icons** — per your steer, defined as a static class constant on each `Provider` subclass (matching the existing `service`/`key`/`display_name` class-attribute pattern in `src/ai_usage/providers/base.py`), not a separate dict:
```python
class Provider:
    ...
    icon: IconRef | None = None  # base.py — default "no icon"
```
Selected + verified against the actual installed package (not guessed):
| Provider key | Icon |
|---|---|
| `web` | `solid/globe` |
| `statusline` | `solid/gauge` |
| `cli-usage`, `cli-status` | `solid/terminal` |
| `app-server` | `solid/server` |
| `github-api` | `brands/github` |
| `entitlements` | `solid/key` |

- `GET /api/v1/catalog` gains `service_icons: dict[str, IconRef]` (from `SERVICE_ICONS`, service→icon, only mapped services present) and `provider_icons: dict[str, IconRef]` (aggregated from every registered `Provider` subclass's `.icon`, keyed by `key`, skipping `None`).
- `frontend/src/types.ts`: add `IconRef` type + both fields on `Catalog`.
- `frontend/src/App.vue`: pass the resolved icon (if any) into each chip — services from `catalog.service_icons[item]`, providers from `catalog.provider_icons[item]`.

## Cluster 4 — Extract a reusable `Chip` component
- New `frontend/src/components/Chip.vue`: props `label`, `active: boolean`, `icon?: IconRef`; emits `click`. Renders the existing `<button class="chip" :class="{active}">` markup plus an optional `<Icon v-if="icon" v-bind="icon" />` before the label.
- Refactor all four `chip-group` blocks in `App.vue` (services/providers/accounts/metrics) to use `<Chip>`, removing the duplicated button markup — only services/providers pass an `icon` prop for now (accounts/metrics have no natural icon source).

## Cluster 5 — Notes/promo rendering: real markdown, position, overflow
- Per your explicit call ("use a proper markdown dependency... the observed data is not under my control"): add **`markdown-it`** to `frontend/package.json` (small, widely used, and critically — `html: false` by default, meaning literal `<...>` in the source is escaped/shown as text rather than executed, which directly satisfies "make sure to escape if using raw HTML" with no extra sanitizer needed). Construct once with `new MarkdownIt({ html: false, linkify: true })`.
- New `renderNoteMarkdown(text: string): string` (in `chart.ts` or a tiny new `frontend/src/markdown.ts`) wrapping `md.renderInline(text)` (inline, not block — these are short one-line banners, not multi-paragraph documents). Used by both `noteTooltipHtml` and the new page banner (Cluster 6) — one implementation, not duplicated.
- Reorder `axisTooltipHtml`'s return: notes first (right after the header), then per-account/provider blocks — currently notes are appended last.
- Fix overflow: add `extraCssText: "max-width: 22rem; white-space: normal; max-height: 60vh; overflow-y: auto;"` to `chartOption()`'s `tooltip` config (a real ECharts option for this, not a CSS hack) — keeps `confine: true` for viewport positioning, lets long content wrap/scroll instead of clipping.
- Update `chart.test.ts`'s `noteTooltipHtml` (markdown rendering, raw-HTML-escaping) and `axisTooltipHtml` (notes-first ordering) tests.

## Cluster 6 — Page-level "active promos" banner
- `frontend/src/App.vue`: computed `activeNotes` using the existing `activeNotesAt(notes.value, Date.now())` (export it from `chart.ts` if not already exported).
- Render each as a `.banner.banner-info` element (new modifier, same base as the existing `.banner`/`.banner-error` "exposed without auth" warning), using `v-html="renderNoteMarkdown(note.text)"` (Cluster 5's helper — same rendering path as the tooltip, so behavior stays consistent between the two places notes appear).
- Add `.banner-info` to `frontend/src/styles/main.scss` following the `.banner-error` pattern, using one of the established 5 semantic colors (secondary/misc reads better than error-red for a promo).

## Cluster 7 — Relative time in the info panels (not the hover tooltip)
- Add `formatRelative(target: Date, now: Date): string` to `frontend/src/time.ts`, built on `formatDuration` (`"in 2h 32m"` / `"2h 32m ago"` / `"just now"`), scoped to `ServicePanels.vue` only — the hover tooltip's `compactWindowDetail` already shows a countdown and is out of scope here per your wording ("for the info display below the graph").
- `windowDetailLines` (`chart.ts`, used only by `windowTooltipHtml`, used only by `ServicePanels.vue`) changes its date-containing lines to `<span title="${absolute}">${relative}</span>` instead of plain absolute text — window start/end and the projected-exhaustion time.
- Update `chart.test.ts`'s `windowTooltipHtml`/`windowDetailLines` tests for the new relative+`title` format.

## Critical files
- `src/ai_usage/icons.py` (new), `pyproject.toml`, `src/ai_usage/api.py` (Cluster 1)
- `frontend/src/components/Icon.vue` (new, Cluster 2)
- `src/ai_usage/graph.py`, `src/ai_usage/providers/base.py` + each provider subclass, `src/ai_usage/api.py`, `frontend/src/types.ts`, `frontend/src/App.vue` (Cluster 3)
- `frontend/src/components/Chip.vue` (new), `frontend/src/App.vue` (Cluster 4)
- `frontend/package.json`, `frontend/src/chart.ts` (or new `frontend/src/markdown.ts`), `frontend/src/chart.test.ts` (Clusters 5 & 7)
- `frontend/src/App.vue`, `frontend/src/styles/main.scss` (Cluster 6)
- `frontend/src/time.ts`, `frontend/src/components/ServicePanels.vue` (Cluster 7)

## Verification
- Backend: `uv run pytest` (new icon-endpoint tests + full suite), `uv run --with ruff ruff check` on touched files.
- Frontend: `yarn vue-tsc --noEmit`, `yarn vitest run`, `yarn build` after each cluster.
- Manual, live, via `ai-usage serve` + browser automation (check real DOM/computed-style state, not screenshots unless asked): confirm brand icons render next to Claude/Codex/Copilot service chips and category icons next to provider chips; confirm a note renders bold/linked (not literal asterisks, and not raw HTML if a source ever contained `<...>`) both in the hover tooltip (now at the top) and the new page banner; confirm a long note wraps/scrolls instead of clipping; confirm ServicePanels shows relative times with the absolute time as a native tooltip on hover.
- Commit each cluster separately (lplp style, active this session) — independently shippable, keeps risk isolated per the same reasoning used for the tree-shaking/tooltip work earlier this session.

## Todos

- [x] Step 1: decouple loading/error from SSE background refresh in App.vue
- [x] Step 2: axis-trigger vertical-slice tooltip in chart.ts
- [x] Step 3: tree-shaken echarts/core import
- [x] Tests + verification (vitest/vue-tsc/build + manual browser check)
- [x] Fix: projection line shows no tooltip when hovered past last real sample
- [x] Cluster 1: backend icon-serving endpoint
- [x] Cluster 2: frontend Icon.vue component
- [x] Cluster 3: service+provider icon mappings, catalog API, App.vue wiring
- [ ] Cluster 4: extract reusable Chip.vue component
- [ ] Cluster 5: markdown rendering + tooltip notes-first + overflow fix
