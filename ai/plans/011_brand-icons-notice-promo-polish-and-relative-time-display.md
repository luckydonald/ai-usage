# Brand icons, notice/promo polish, and relative-time display

## Context
Follow-up round of dashboard polish, six requests bundled together. All were investigated against the real code (not guessed) before this plan was written: three research agents covered filter-chip generation, notes/tooltip/ServicePanels behavior, and the FastAPI app's routing/static-serving conventions; two more verified the actual icon package contents by unzipping/running it in isolation. Findings below are load-bearing for the design, not assumptions.

## Key findings from research
- **Chips are 100% dynamic** — `frontend/src/App.vue`'s service/provider chip groups render the raw `service`/`provider` strings straight from `/api/v1/catalog`, no Vue-side display-name mapping. The one existing "service → visual property" precedent (color) is done **backend-side**: `src/ai_usage/graph.py`'s `SERVICE_BASE_COLORS` dict, baked into each `GraphSeries.color` before it reaches the frontend. Icons should follow the same pattern.
- **`fontawesomefree` (the originally-named pip package) has no Claude/OpenAI/Copilot brand icons at all** — confirmed by unzipping the actual wheel. Per your decision, using **`fontawesome-free-pack`** instead (latest 7.3.0, actively maintained, a Rust-backed redistribution of the real `@fortawesome/fontawesome-free` npm package's assets). Confirmed by running it in an isolated venv: **`claude` and `openai` brand icons exist, `copilot` does not exist in this package (or upstream Font Awesome at all)** — flagged as a known gap, not a blocker (see Cluster 1).
- This package has **no on-disk SVG files** — it's a compiled extension; icons come from `get_icon(f"{family}/{slug}")` at runtime, returning an object with `.svg` (string). No `svgs/brands/*.svg` directory to serve statically.
- `src/ai_usage/api.py` has **no `APIRouter`** — every route is a plain `@app.get(...)` inside `create_app()`. Critically, there's a catch-all `@app.get("/{path:path}")` SPA-fallback route (`api.py:223`, only registered when the frontend dist exists) that will **shadow any route declared after it** — new routes must go above that block. No existing `Cache-Control`/`RedirectResponse` usage anywhere to copy; this introduces the pattern fresh.
- Notes/promo text **already contains literal markdown** (`**bold**`, confirmed via the GrowthBook banner and its pinned test fixture) and is rendered completely raw today (`noteTooltipHtml` wraps the whole string in `<strong>`, no parsing). No markdown library exists in the frontend; no HTML sanitizer either.
- ECharts tooltip has `confine: true` (repositions to stay in-bounds) but **no width/wrap control** — long content just clips against the edge instead of wrapping. There's a dedicated ECharts option for exactly this (`tooltip.extraCssText`), not yet used.
- `ServicePanels.vue` doesn't build its own date strings — it dumps `windowTooltipHtml(...)`'s pre-built HTML string via `v-html`. All of `windowTooltipHtml`/`windowDetailLines`'s absolute-time formatting lives in `chart.ts`, and (confirmed) **`windowTooltipHtml` is called from nowhere else** — safe to change its date rendering without touching the hover tooltip (which uses its own separate `compactWindowDetail`, added in a prior session round).
- `frontend/src/time.ts`'s `formatDuration(ms)` already handles signed durations (`"2h 32m"`, `"-3d 4h"`, `"<1m"`) — directly reusable as the basis for a new relative-time helper.

## Cluster 1 — Backend icon-serving endpoint
- Add `fontawesome-free-pack` to `pyproject.toml` dependencies.
- New routes in `src/ai_usage/api.py`, inserted **above** the `if paths.frontend.exists():` block (≈ line 217) alongside the other `@app.get("/api/v1/...")` handlers:
  - `GET /img/icons/fontawesomefree/v{version}/{family}/{icon}.svg` — validate `family` is one of `brands`/`solid`/`regular`; validate `{version}` matches `importlib.metadata.version("fontawesome-free-pack")` (we can only ever serve the one version that's actually installed — mismatch is a 404, not an error); call `get_icon(f"{family}/{icon}")`; `None` → 404; otherwise `Response(content=result.svg, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=31536000, immutable"})`.
  - `GET /img/icons/fontawesomefree/latest/{family}/{icon}.svg` — `RedirectResponse(url=f"/img/icons/fontawesomefree/v{version}/{family}/{icon}.svg", status_code=307, headers={"Cache-Control": "public, max-age=86400"})`.
  - Add `RedirectResponse` and `Response` to the existing `fastapi.responses` import.
- **Copilot gap**: no Copilot brand icon exists in this package or upstream Font Awesome. The endpoint returns a clean 404 for `copilot.svg` — the frontend `<Icon>` component (Cluster 2) needs to tolerate that (broken-image fallback or a generic placeholder), and the service→icon mapping (Cluster 3) simply omits an icon for `copilot`. Sourcing a Copilot glyph from elsewhere is explicitly out of scope for this pass.
- Tests in `tests/test_api.py`: known-good icon (e.g. `brands/claude`) returns 200 + `image/svg+xml` + immutable cache header; unknown icon 404; `/latest/...` returns a 307 to the versioned URL with the ~1-day cache header; wrong version in the versioned path 404s.

## Cluster 2 — Frontend `<Icon>` component
- New `frontend/src/components/Icon.vue`: props `icon` (required), `source = "fontawesomefree"`, `family = "brands"`, `version = "latest"`, all defaulted per your spec. Renders `<img :src="\`/img/icons/${source}/${version}/${family}/${icon}.svg\`" :alt="icon" class="icon" />` — plain `<img>` is sufficient (browser honors the backend's cache headers; brand marks are shown in their own colors, not recolored, so no need to inline-fetch+embed the SVG for CSS `fill` control).
- Since brand SVGs are typically single-color and may not read well on a matching-color background in dark mode, wrap in a small rounded/padded chip background (reuse the existing `.chip`/`.account-chip` pill pattern from `frontend/src/styles/main.scss`) rather than bare — cheap insurance against a dark icon vanishing on a dark toolbar.

## Cluster 3 — Filter chips get icons (service chips only, not provider-key chips)
- Add a `SERVICE_ICON_SLUGS: dict[str, str]` mapping in `src/ai_usage/graph.py` (next to `SERVICE_BASE_COLORS`, same pattern): `{"claude": "claude", "codex": "openai"}` — `codex` maps to the `openai` glyph per your `~~codex~~` strikethrough (i.e. show OpenAI's mark for the Codex service), `copilot` intentionally has no entry (see Cluster 1's gap).
- Extend `GET /api/v1/catalog`'s response with a `service_icons: dict[str, str]` field (only services that have a mapped icon are present; frontend treats a missing key as "no icon").
- **Scoping note**: only `service` chips get icons — `provider` chips (`web`/`statusline`/`cli-usage`/`app-server`/...) are provider *keys*, not brand identifiers, so there's no natural icon mapping for them. Flagging this explicitly rather than silently deciding; can revisit if you want provider-level icons too (e.g. a generic "terminal" vs "globe" glyph for CLI vs web providers), but that wasn't in the original ask.
- `frontend/src/App.vue`: extend `Catalog`/`fetchCatalog` types for the new field, prepend `<Icon v-if="catalog.service_icons[item]" :icon="catalog.service_icons[item]" />` inside the services chip button template.

## Cluster 4 — Notes/promo rendering: markdown, position, overflow
- Add a small trusted markdown-to-HTML helper (no new frontend dependency — the only syntax actually observed is `**bold**` and `[text](url)`): escape HTML entities first (so no literal tag can ever sneak through even from an untrusted-ish source like the GrowthBook banner), then regex-replace escaped-safe `**bold**` → `<strong>`, `[text](url)` → `<a href="..." target="_blank" rel="noopener noreferrer">`. Export as `renderNoteMarkdown(text: string): string` from `frontend/src/chart.ts` (or a new tiny `frontend/src/markdown.ts` if that reads cleaner) — used by both `noteTooltipHtml` and the new page banner (Cluster 5), so there's exactly one implementation.
- Reorder `axisTooltipHtml`'s return: notes first (right after the header), then the per-account/provider blocks — currently notes are appended last.
- Fix overflow: add `extraCssText: "max-width: 22rem; white-space: normal; max-height: 60vh; overflow-y: auto;"` to `chartOption()`'s `tooltip` config (a real ECharts option for exactly this, not a CSS hack this time) — keeps `confine: true` for viewport positioning, but lets long note content wrap and scroll instead of clipping.
- Update `chart.test.ts`'s `noteTooltipHtml` tests (markdown rendering) and `axisTooltipHtml` tests (notes-first ordering).

## Cluster 5 — Page-level "active promos" banner
- `frontend/src/App.vue`: new computed `activeNotes` calling the existing `activeNotesAt(notes.value, Date.now())` (already exported from `chart.ts`, currently only used internally there — export it if not already, reuse rather than duplicate the active-window predicate).
- Render each active note as a `.banner.banner-info` element (new modifier class, same base as the existing `.banner`/`.banner-error` "exposed without auth" warning at `App.vue`), placed above/alongside that existing banner, each using `v-html="renderNoteMarkdown(note.text)"` (Cluster 4's helper).
- Add `.banner-info` to `frontend/src/styles/main.scss` following the exact `.banner-error` pattern, using one of the established 5 semantic colors (secondary "sky surge" or misc "blush pop" reads better than error-red for a promo, not a warning).

## Cluster 6 — Relative time in the info panels (not the hover tooltip)
- Add `formatRelative(target: Date, now: Date): string` to `frontend/src/time.ts`, built on the existing `formatDuration` (e.g. `"in 2h 32m"` / `"2h 32m ago"` / `"just now"` for sub-minute), scoped to `ServicePanels.vue`'s display only — the hover tooltip's own `compactWindowDetail` (added last round) already shows a duration-based countdown and is explicitly out of scope here per your wording ("for the info display below the graph").
- `windowDetailLines` (`chart.ts`, used only by `windowTooltipHtml`, used only by `ServicePanels.vue` — confirmed no other caller) changes its date-containing lines to emit `<span title="${absolute}">${relative}</span>` instead of plain absolute text, for window start/end and the projected-exhaustion time.
- Update `chart.test.ts`'s `windowTooltipHtml`/`windowDetailLines`-covering tests for the new relative+`title` format.

## Critical files
- `pyproject.toml`, `src/ai_usage/api.py` (Cluster 1)
- `frontend/src/components/Icon.vue` (new, Cluster 2)
- `src/ai_usage/graph.py`, `src/ai_usage/api.py`, `frontend/src/types.ts`, `frontend/src/App.vue` (Cluster 3)
- `frontend/src/chart.ts`, `frontend/src/chart.test.ts` (Clusters 4 & 6)
- `frontend/src/App.vue`, `frontend/src/styles/main.scss` (Cluster 5)
- `frontend/src/time.ts`, `frontend/src/components/ServicePanels.vue` (Cluster 6)

## Verification
- Backend: `uv run pytest` (new icon-endpoint tests + full suite), `uv run --with ruff ruff check` on touched files.
- Frontend: `yarn vue-tsc --noEmit`, `yarn vitest run`, `yarn build` after each cluster.
- Manual, live, via `ai-usage serve` + browser automation (established pattern this session — check real DOM/computed-style state, not screenshots unless asked): confirm an icon actually renders next to the Claude/Codex service chips, confirm a note renders bold/linked (not literal asterisks) both in the hover tooltip (at the top now) and the new page banner, confirm a long note wraps/scrolls instead of clipping off the chart edge, confirm ServicePanels shows relative times with the absolute time as a native tooltip on hover.
- Commit each cluster separately (lplp style, already active this session) — they're independently shippable and this keeps risk isolated per the same reasoning used for the tree-shaking/tooltip work earlier.
