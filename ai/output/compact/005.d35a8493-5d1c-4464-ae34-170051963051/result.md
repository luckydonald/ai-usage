<analysis>
This is a long multi-session conversation covering many distinct chart/tooltip/CLI/backend fixes. I need to trace chronologically, but given the length, I'll focus most detail on the most recent, still-in-progress work (the "Brand icons, notice/promo polish, and relative-time display" plan), while still capturing the full arc so context isn't lost.

Early parts of the conversation (already compacted before this window began, per the initial summary) covered:
- Investigation into Claude's web promo banner API (GrowthBook feature flag `19186470`, djb2 hashing, PII redaction of captured reference JSON).
- A large chart/tooltip rework plan (plan file `009_fix-the-chart-s-remount-reanimate-bug-add-a-real-vertical-sl.md`): fixed the root cause of chart remount/reanimate (App.vue's `loading` flag toggling v-if on every SSE tick), added axis-trigger vertical-slice tooltip, tree-shook echarts, fixed a tooltip-fighting CSS race (solved with a `:deep()` scoped CSS `!important` rule since Vue's scoped-CSS attribute-scoping doesn't tag ECharts' runtime-injected DOM), unified two competing tooltips into one, fixed step-line "held value" snapping bug, grouped/compacted the merged tooltip by account+provider, added window-reset time+countdown to tooltip.
- Backend: pulled Claude's web promo banner into the existing `ClaudeWebUsageProvider` (not a new provider), added `extract_claude_web_notes()`.
- Backend: fixed `Crawler.run()` to crawl immediately on startup instead of waiting for possibly-future `next_run_at` (extracted shared `Crawler.crawl(accounts, reason)` method).
- Backend: researched (not implemented) replacing `textual` with `questionary` for the CLI's list-picker UI (plan `010_replace-textual-with-a-lightweight-list-picker-library.md`).
- All work committed via lplp commit style (active this session), each commit written to `ai/git/pending-commit.md` first, following the format `[where] component: ai: Run: <summary>.`
- `ai/plans/pending.md` was continuously updated to track backlog items, marking each as fixed/implemented/researched with details.
- `main.test.ts` had a known flake under parallel test-runner load (passes reliably in isolation) — not a real regression, confirmed multiple times.

Then the current major task began: user invoked `/plan` with a large multi-part request (verbatim, this is critical to preserve):
```
We're getting there. Good addition with the badges. Visual separation and grouping helps, just a wall of text is boring indeed.
- I want to use the brand icons from the pip package `fontawesomefree` (claude, copilot, ~~codex~~ openai, …)
  - for that create an endpoint serving them at `/img/icons/fontawesomefree/v{package-version}/brands/{icon}.svg`.
  - that route shall be cached, they don't update
  - also for easy frontend embedding provide `/img/icons/fontawesomefree/latest/brands/{icon}.svg` as redirect to that version, however as a 1-day cached redirect.
  - create a svg embed `<Icon source="frontawesomefree" family="brand" version="latest" icon="claude">`, where the params except `icon` already have those defaults.
  - if easier for routing with static file dir, `/api/img/…` would be possible, too.
- resets of windows in the past show `(<1m)`
- the boosted limit display should be rendered as markdown, and rather overflow than causing the tooltip to go out of bounds
  - also it should be at the top.
  - show all currently active ones at the top of the page.
- for the info display below the graph, I want relative times, with the absolute ones as tooltip
- the filter badges up top should also contain icons. Explain me how it currently figures out which filters to display, so I know how we best apply the icons
  - if it is a hardcoded thing in vue, then the icons would too.
  - if it's generated from the providers, it can be a constant in those classes
```

I entered plan mode, launched 3 parallel Explore agents:
1. Filter badge generation and catalog data flow — found chips are 100% dynamic from `/api/v1/catalog`, no Vue hardcoding; the existing "service→visual property" precedent (color) is backend-side (`graph.py`'s `SERVICE_BASE_COLORS`), not frontend. Confirmed exact `service` values in code: `claude`, `codex`, `copilot`. Confirmed `Provider.display_name` exists but isn't propagated to any API response.
2. fontawesomefree package layout + static asset serving in api.py — critical finding: `fontawesomefree` 6.6.0 (only PyPI version) has **no claude/openai/copilot brand icons at all** (verified by downloading and unzipping the actual wheel: `svgs/brands/*.svg`, 984 files, checked exhaustively — none of claude/openai/copilot/gpt exist). Also found: `api.py` has no `APIRouter`, all routes are `@app.get(...)` inside `create_app()`; there's a catch-all `@app.get("/{path:path}")` SPA-fallback (only registered when frontend dist exists) that will shadow any route declared after it — new routes must go above it (~line 217-236). No existing `Cache-Control`/`RedirectResponse` pattern in the codebase.
3. Notes/promo rendering, tooltip overflow, ServicePanels time display — confirmed notes text already contains literal markdown (`**bold**`, pinned in a test fixture), rendered completely raw (`noteTooltipHtml` just wraps in `<strong>`, no parsing); no markdown lib or sanitizer exists in frontend; only `v-html` usage is `ServicePanels.vue:62` (rendering `windowTooltipHtml` output) plus ECharts' own tooltip formatter innerHTML injection. `tooltip.confine: true` repositions but doesn't prevent clipping (no width/wrap CSS). `ServicePanels.vue` gets ALL its date strings from `windowTooltipHtml`/`windowDetailLines` in `chart.ts` (only caller), which uses `.toLocaleString()` absolute times exclusively; `formatDuration(ms)` in `time.ts` already exists and handles signed durations, no relative-time helper exists yet.

Given the fontawesomefree blocker (no claude/openai/copilot icons), I used AskUserQuestion to ask how to handle it. User chose "Use `fontawesome-free-pack` then, that's up to date." — a DIFFERENT package name than what they originally specified in the query. I then launched another agent to verify this new package. Findings: `fontawesome-free-pack` (exact name) exists on PyPI, latest 7.3.0 (2026-07-01), actively maintained (5 releases over ~10 months), is a Rust-compiled extension (PyO3/maturin) with **no on-disk SVG files** — icons accessed via `get_icon(f"{family}/{slug}")` returning an object with `.svg` string; confirmed `BRANDS_CLAUDE`, `BRANDS_OPENAI`, `BRANDS_MICROSOFT`, `BRANDS_GITHUB` exist but **no `BRANDS_COPILOT`/`BRANDS_GITHUB_COPILOT`/`BRANDS_MICROSOFT_COPILOT`** — confirmed via runtime lookup returning `None`. License `(CC-BY-4.0 AND OFL-1.1 AND MIT)`, redistributes `@fortawesome/fontawesome-free` npm assets. Importable module: `fontawesome_free_pack`; `importlib.metadata.version("fontawesome-free-pack")` (hyphenated) is correct for version lookup.

I wrote a first draft plan to `/home/user/.claude/plans/fluttering-growing-bumblebee.md` using the `fontawesomefree`→`fontawesome-free-pack` swap but keeping the URL path segment as literally "fontawesomefree" (not yet renamed), noting Copilot as an unsolved gap (route would just 404), 6 clusters (icon endpoint, Icon.vue, service-chip icons only, notes markdown+position+overflow via hand-rolled regex, page banner, ServicePanels relative time). Called `ExitPlanMode` — user's tool result initially showed "approved" but then this exact same message was immediately followed by a **user interruption via a fresh `/plan` command with identical-looking but actually corrective content** (the real substantive feedback), which is captured below.

The critical, verbatim user feedback that reshaped the plan (delivered as `/plan` command args, this is a genuine user turn, not a duplicate — I want to preserve this exactly):
```
Plan changes:
- Change the svg URL to `fontawesome-free-pack` then, to keep it straight forward.
- Brands `copilot` should be included since v`7.3.0`. Either way it should be added to `SERVICE_ICON_SLUGS`.
- Feel free to extract the chip as component for better reuse.
- Yeah, I want provider icons too, so that's why I was thinking about maybe putting those inside the `class` definition as static constant.
  - you can go ahead and select those icons already from the available free icons.
  - with now needing brand and free, therefore pack, version, set, name should be defined properly, instead of just the name, so others can be used in the future.
- Use a proper markdown dependency to be future proof - the observed data is not under my control.
- Make sure to escape if using raw HTML.
```

I re-verified the Copilot claim directly myself (not trusting either side blindly) by creating a fresh isolated venv (`/tmp/fapack-check`), installing `fontawesome-free-pack==7.3.0` fresh, and checking: `dir(fp)` for any `COPILOT`/`PILOT` substring across all 2160 constants — zero matches; also tried `get_icon('brands/copilot')`, `get_icon('brands/github-copilot')`, `get_icon('brands/microsoft-copilot')` — all `None`. This **contradicted the user's stated belief** that Copilot should be included since v7.3.0. Per my principle of trusting direct observation over recalled/stated claims, I flagged this clearly via `AskUserQuestion` rather than silently complying with either the false premise or silently overriding the user. Question: "How should SERVICE_ICON_SLUGS handle Copilot given it doesn't exist?" Options: omit it / use GitHub's icon as a stand-in / something else. **User selected: "Use GitHub's icon as a stand-in."**

I then verified candidate provider-icon slugs in another scratch venv (`/tmp/fa-slug-check`) before finalizing: `solid/globe` ✅, `solid/gauge` ✅, `solid/terminal` ✅, `solid/square-terminal` ❌ (dropped), `solid/server` ✅, `brands/github` ✅, `solid/key` ✅, `solid/id-badge` ✅, `solid/certificate` ✅, `brands/claude` ✅, `brands/openai` ✅. Cleaned up both scratch venvs with `rm -rf` afterward.

I then rewrote the ENTIRE plan file (`/home/user/.claude/plans/fluttering-growing-bumblebee.md`) incorporating all six pieces of feedback, and called `ExitPlanMode` again — this was approved by the user (tool result: "User has approved your plan. You can now start coding.").

Immediately after approval, I began execution: created 3 tasks via `TaskCreate` (Cluster 1: backend icon-serving endpoint; Cluster 2: frontend Icon.vue component; Cluster 3: service+provider icon mappings, catalog API, App.vue wiring) — these tasks are still `[pending]`, none started yet, no code written yet for this feature set.

Then the user sent **another `/plan` command with byte-identical-looking args** to the corrective one above ("Plan changes: - Change the svg URL to fontawesome-free-pack then... Make sure to escape if using raw HTML."), which re-enabled plan mode. I investigated via `git status`/`git diff` and determined this was a **stray duplicate delivery of the same already-processed command** (not a new distinct user instruction) — the plan file content already fully reflected every one of these points. I confirmed via `git diff` that `ai/plans/011_brand-icons-notice-promo-polish-and-relative-time-display.md` (a project-committed snapshot, auto-saved by some harness hook at an earlier `ExitPlanMode` call, distinct from the authoritative `/home/user/.claude/plans/fluttering-growing-bumblebee.md` scratch file I'm instructed to edit) was stale — it still had the FIRST-draft content (literal "fontawesomefree" in the URL, no Copilot resolution) plus a stray uncommitted one-line typo edit (`v{version}` → `-v{version}` in a redirect URL, that I did not intentionally make — likely a duplicate-processing artifact). I read the authoritative plan file in full and confirmed it already contained the complete, corrected 7-cluster plan matching all six feedback points, then called `ExitPlanMode` a second time (approved again, identical content).

I then began correcting the stale `ai/plans/011_...md` project-committed file to match the authoretative plan (recognizing it should be synced since it's the project's persistent record), and had just run `diff` confirming the mismatch and `Read` on both files (the stale one showing only 5 lines read, the authoritative one showing the full ~106-line final plan) when the conversation was interrupted for this summary request.

No actual implementation code (Clusters 1-7) has been written yet for this icon/markdown/relative-time plan — I was still in the "sync the stale plan snapshot file" cleanup step, about to proceed to Cluster 1 implementation.
</analysis>

<summary>
1. Primary Request and Intent:
   The immediately active task (this session's current focus) is a 7-cluster plan titled "Brand icons, notice/promo polish, and relative-time display," approved by the user, covering:
   - Backend endpoint serving Font Awesome brand/category icons, versioned + cached, plus a `latest` redirect variant, plus a Vue `<Icon>` embed component.
   - Both service-level (brand) AND provider-level (category) icons on the filter chips, with icons defined as a static class constant on each `Provider` subclass (backend), addressed via a structured 4-field `IconRef` (pack/version/set/name) everywhere — not bare strings — "so others can be used in the future."
   - Extract a reusable `Chip` Vue component (currently 4x-duplicated markup in `App.vue`).
   - Render promo/notice text as real markdown (via a proper dependency, not hand-rolled regex, since "the observed data is not under my control"), with mandatory escaping of any raw HTML in the source; move notes to the TOP of the hover tooltip; fix tooltip overflow so long notes wrap/scroll instead of clipping (not `confine`-squished); also show all currently-active notes as a banner at the top of the page (not just in the tooltip).
   - Fix: past-window resets currently show a misleading `(<1m)` countdown (a leftover bug flagged by the user, not yet actually fixed in code — flagged in the original `/plan` request but not explicitly re-addressed as a standalone cluster in the final 7-cluster plan; worth confirming with the user whether this is still expected to be handled, since the final plan doesn't have an explicit cluster for it).
   - `ServicePanels.vue` ("the info display below the graph") should show relative times with absolute times as a native `title` tooltip — explicitly scoped to NOT touch the hover-tooltip's own already-existing countdown display.
   - This entire plan followed from the user's earlier compliment "We're getting there. Good addition with the badges. Visual separation and grouping helps, just a wall of text is boring indeed" (i.e., positive feedback on prior tooltip-grouping work, motivating this next round of polish).

2. Key Technical Concepts:
   - `fontawesome-free-pack` (PyPI, latest 7.3.0) — Rust/PyO3-compiled extension, no on-disk SVGs, accessed via `get_icon(f"{family}/{slug}")` returning `.svg` string attribute; distribution name has a hyphen, import name has underscores (`fontawesome_free_pack`).
   - `IconRef` structured type (4 dimensions: `pack`, `version`, `set`, `name`) as the addressing scheme across backend constants, API JSON payloads, and frontend component props — explicit user requirement, not my own initial design (my first draft just used bare icon-name strings).
   - FastAPI route-ordering hazard: a catch-all `@app.get("/{path:path}")` SPA-fallback (conditionally registered only when the built frontend dist exists) will shadow any route registered after it in `src/ai_usage/api.py`; new routes must be declared above that block (~api.py line 217-236).
   - `Cache-Control` header patterns to introduce fresh (no existing precedent in the codebase): `public, max-age=31536000, immutable` for version-pinned icon SVGs; `public, max-age=86400` for the `.../latest/...` redirect.
   - ECharts `tooltip.extraCssText` option — the correct built-in mechanism for wrap/scroll/max-width control on tooltip content (distinct from `confine: true`, which only repositions to stay in-viewport, doesn't control content overflow).
   - `markdown-it` (chosen per explicit user instruction to use "a proper markdown dependency," not hand-rolled regex) — configured with `{ html: false, linkify: true }`; `html: false` is critical since it makes markdown-it escape literal `<...>` in source text rather than passing it through as executable HTML, directly satisfying the user's "make sure to escape if using raw HTML" requirement with no extra sanitizer library needed.
   - Existing backend precedent for "service → visual property" mapping: `src/ai_usage/graph.py`'s `SERVICE_BASE_COLORS: dict[str, str]` — baked into `GraphSeries.color` before reaching the frontend; the new icon mapping is designed to mirror this exact pattern (`SERVICE_ICONS: dict[str, IconRef]`).
   - `Provider` base class (`src/ai_usage/providers/base.py`) already has class-attribute pattern for `service`/`key`/`display_name`; plan adds `icon: IconRef | None = None` as another class attribute, set per concrete Provider subclass — this was the user's explicit steer ("putting those inside the `class` definition as static constant"), not my own first idea (I'd originally proposed a separate dict).
   - `windowTooltipHtml`/`windowDetailLines` (`chart.ts`) are called from nowhere except `ServicePanels.vue` — confirmed via research agent, meaning date-format changes there are safely scoped and won't affect the hover tooltip's own separate `compactWindowDetail` path.
   - `activeNotesAt(notes, atMs)` already exists in `chart.ts` (internal use only so far) — reusable for the new page-level banner's "currently active" filter, avoiding duplicate logic.
   - lplp commit-style workflow remains active for this session: write message to `ai/git/pending-commit.md` first (after `rm ai/git/pending-commit.md || echo 'was gone'`), commit with `-F`, fold `ai:`-prefixed auto-commits (`ai: updated prompt`, `ai: save decision <slug>`, `ai: agent <id> results`, `ai: save plan <NNN>_<slug>`) into the substantive commit via `git reset --soft` + re-stage + re-commit, never `git add -A`/`.`.
   - Plan-mode workflow: `/home/user/.claude/plans/fluttering-growing-bumblebee.md` is the ONE authoritative, editable-in-plan-mode scratch plan file; `ai/plans/NNN_<slug>.md` files are separate project-committed snapshots auto-saved by a harness hook at `ExitPlanMode` time — these can go stale/out-of-sync with the authoritative file if `ExitPlanMode` fires multiple times across a correction cycle, and need manual re-sync.

3. Files and Code Sections:
   - `/home/user/.claude/plans/fluttering-growing-bumblebee.md` (the authoritative, currently-approved plan file; NOT part of the git repo)
     - Full final content (as last read, 106 lines) — this is the live spec for all remaining implementation work. Key excerpts:
     ```python
     # src/ai_usage/icons.py (new)
     class IconRef(NamedTuple):
         pack: str = "fontawesome-free-pack"
         version: str = "latest"
         set: Literal["brands", "solid", "regular"] = "brands"
         name: str
     ```
     ```python
     SERVICE_ICONS: dict[str, IconRef] = {
         "claude": IconRef(set="brands", name="claude"),
         "codex": IconRef(set="brands", name="openai"),
         "copilot": IconRef(set="brands", name="github"),  # stand-in, no real Copilot icon exists
     }
     ```
     ```python
     class Provider:
         ...
         icon: IconRef | None = None  # base.py default
     ```
     Provider-key → icon table (verified against the real package):
     | Provider key | Icon |
     |---|---|
     | `web` | `solid/globe` |
     | `statusline` | `solid/gauge` |
     | `cli-usage`, `cli-status` | `solid/terminal` |
     | `app-server` | `solid/server` |
     | `github-api` | `brands/github` |
     | `entitlements` | `solid/key` |
     Route specs:
     - `GET /img/icons/fontawesome-free-pack/v{version}/{set}/{name}.svg` — validate `set`, validate version matches installed package version, resolve via `get_icon`, 404 on miss, else `Response(content=result.svg, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=31536000, immutable"})`.
     - `GET /img/icons/fontawesome-free-pack/latest/{set}/{name}.svg` — `RedirectResponse(url=f"/img/icons/fontawesome-free-pack/v{version}/{set}/{name}.svg", status_code=307, headers={"Cache-Control": "public, max-age=86400"})`.
     - Both must be registered in `src/ai_usage/api.py` ABOVE the `if paths.frontend.exists():` block (~line 217).
     `Icon.vue` spec: props `icon` (required), `source = "fontawesome-free-pack"`, `family = "brands"`, `version = "latest"`; renders `<img :src="\`/img/icons/${source}/${version}/${family}/${icon}.svg\`" :alt="icon" class="icon" />`, wrapped in a chip-pill background (reusing `.chip`/`.account-chip` styling).
     `Chip.vue` spec: props `label`, `active: boolean`, `icon?: IconRef`; emits `click`; renders existing `<button class="chip">` markup + optional `<Icon v-if="icon" v-bind="icon" />`.
     Markdown spec: `new MarkdownIt({ html: false, linkify: true })`; new `renderNoteMarkdown(text: string): string` (in `chart.ts` or new `frontend/src/markdown.ts`) wrapping `md.renderInline(text)`; used by both `noteTooltipHtml` and the new page banner.
     Tooltip fixes: reorder `axisTooltipHtml` to put notes first (right after header) instead of last; add `extraCssText: "max-width: 22rem; white-space: normal; max-height: 60vh; overflow-y: auto;"` to `chartOption()`'s `tooltip` config.
     Page banner spec: `App.vue` computed `activeNotes` via `activeNotesAt(notes.value, Date.now())` (export from `chart.ts` if needed); render `.banner.banner-info` elements with `v-html="renderNoteMarkdown(note.text)"`; add `.banner-info` to `main.scss` using one of the 5 established semantic colors.
     ServicePanels relative-time spec: new `formatRelative(target: Date, now: Date): string` in `time.ts` built on `formatDuration`; `windowDetailLines` changes date-containing lines to `<span title="${absolute}">${relative}</span>`.
     Critical files list and Verification section (backend `uv run pytest`/ruff, frontend `vue-tsc`/`vitest`/`yarn build` per cluster, manual live browser verification via `ai-usage serve`, commit each cluster separately per lplp style).
   - `ai/plans/011_brand-icons-notice-promo-polish-and-relative-time-display.md` (project-committed, git-tracked snapshot)
     - Currently STALE — still contains the first-draft content (literal `fontawesomefree` URL segment, no Copilot resolution, hand-rolled-regex markdown approach, no provider icons, no Chip extraction) PLUS one stray uncommitted single-line edit (a redirect URL string accidentally mutated to `.../fontawesomefree/-v{version}/...` — an extra stray `-` character, not intentional).
     - `git diff --stat` showed only 1 line changed vs HEAD; I had just re-read both this file (5 lines) and the authoritative file (full 106 lines) side-by-side to prepare a sync-fix, but had not yet written the corrected content back to this file when interrupted.
   - No other project source files have been modified yet for this specific plan (Clusters 1-7 are all still `[pending]` — zero implementation code written).
   - Files referenced/confirmed-but-not-yet-edited by research (from the 4 investigation agents), which the next implementation steps will touch:
     - `pyproject.toml` — needs `fontawesome-free-pack` added to `dependencies`.
     - `src/ai_usage/api.py` — needs new `RedirectResponse`/`Response` imports and the two new icon routes inserted above line ~217; already has `GET /api/v1/catalog` at ~line 99-118 (needs `service_icons`/`provider_icons` fields added), plus existing routes: `/api/v1/health` (94), `/api/v1/latest` (121), `/api/v1/series` (142), `/api/v1/notes` (168), `/api/v1/events` (183), conditional `/api/v1/sentry/sample-error` (210-215).
     - `src/ai_usage/graph.py` — has `SERVICE_BASE_COLORS` (~lines 26-32), `PALETTE` (~11-20), `brand_color_variant()` (~56-66), `generated_color()` (~69-76); needs new `SERVICE_ICONS` dict added alongside.
     - `src/ai_usage/providers/base.py` — `Provider` class (~lines 33-40) declares `service`, `key`, `display_name`, `experimental`, `configuration_fields`, `login_url`, `login_hint`; needs new `icon: IconRef | None = None` attribute.
     - Provider subclasses needing `.icon =` set: services `claude`/`codex`/`copilot` across `claude.py`, `codex.py`, `copilot.py`, `web.py` (keys: `web`, `statusline`, `cli-usage`, `cli-status`, `app-server`, `github-api`, `entitlements`).
     - `frontend/src/App.vue` — `services`/`providers`/`accounts`/`metricOptions` computeds (~lines 30-48), chip-group templates (~lines 221-260) render raw strings directly (no display-name mapping); `notes` ref (~line 12), `loadNotes()` (~120-122), `onMounted` (~154), SSE handler (~160); existing `.banner.banner-error` precedent (~line 179) driven by `exposed` computed (~line 27).
     - `frontend/src/types.ts` — `CatalogMetric` (25-31), `Account` (13-23), `Catalog` (33-37), `NoteRange` (81-87) — none currently have `display_name`/`icon` fields; needs new `IconRef` type + `service_icons`/`provider_icons` fields on `Catalog`.
     - `frontend/src/chart.ts` — `noteTooltipHtml` (~166-170, currently `` `<strong>${note.text}</strong>` `` raw), `activeNotesAt` (~207-213), `axisTooltipHtml` (~253-298, notes appended last at line ~297), tooltip config with `confine: true` (~424-431), `windowDetailLines`/`windowTooltipHtml` (used only by ServicePanels).
     - `frontend/src/components/ServicePanels.vue` — `statsHtml()` (~50-53) calls `windowTooltipHtml(entry.item, entry.window, new Date(), props.accountLabels, false)`, rendered via `<p v-html="statsHtml(entry)" />` (line 62) — only `v-html` usage besides ECharts' own internal tooltip injection.
     - `frontend/src/time.ts` — `formatDuration(ms)` (80-90) exists; no relative-time helper yet.
     - `frontend/src/styles/main.scss` — `.banner`/`.banner-error` (112-123) precedent to extend with `.banner-info`.
     - `frontend/package.json` — no markdown/sanitizer/icon deps currently; needs `markdown-it` added.
     - `frontend/src/chart.test.ts` — has `describe("noteTooltipHtml", ...)` (122-141) and `describe("axisTooltipHtml", ...)` (310-380, including a test pinning "notes appended once, not per series" at end) that will need rewriting once markdown + notes-first ordering land; no dedicated ServicePanels test file exists yet.
   - `pyproject.toml` — confirmed `requires-python = ">=3.14"`, no existing SVG/icon dependency; full deps list: `aiosqlite`, `alembic`, `click`, `cryptography`, `curl-cffi`, `fastapi`, `fastscheduler`, `httpx`, `pexpect`, `platformdirs`, `pydantic`, `pyyaml`, `sentry-sdk[fastapi]`, `sqlalchemy[asyncio]`, `textual`, `typer`, `uvicorn`.

4. Errors and fixes:
   - **First research pass named the wrong package** (`fontawesomefree` 6.6.0) — I verified it by actually downloading and unzipping the real wheel rather than trusting the user's original query text; confirmed zero claude/openai/copilot brand SVGs exist in it. Fixed by asking the user via `AskUserQuestion` rather than silently picking a workaround; user redirected to `fontawesome-free-pack`.
   - **User's stated belief about Copilot ("should be included since v7.3.0") directly contradicted by my own re-verification** — I did not blindly trust either the user's claim or my own prior finding; I re-ran a fresh isolated-venv install of the exact version and exhaustively grepped all 2160 constants plus tried 3 plausible slug names (`copilot`, `github-copilot`, `microsoft-copilot`), all returned `None`/no match. I explicitly told the user what I verified ("Re-checked directly: fontawesome-free-pack 7.3.0 has zero Copilot-related constants...") and asked how to proceed via `AskUserQuestion` rather than either silently complying with the false premise or silently overriding the user's instruction. **User feedback/resolution: "Use GitHub's icon as a stand-in."** — this is now locked into the plan.
   - **`solid/square-terminal` guessed as a candidate provider icon but doesn't exist** — caught via direct verification in a scratch venv before finalizing the plan (not left as an assumption); dropped in favor of reusing `solid/terminal` for both `cli-usage` and `cli-status` keys.
   - **Stray duplicate `/plan` command delivery** — the exact same corrective feedback ("Plan changes: - Change the svg URL to fontawesome-free-pack then...") appeared to fire a second time, re-entering plan mode. I did not re-do the research or re-ask the already-resolved Copilot question; I verified via `git status`/`git diff` that this was a stray re-delivery of an already-fully-incorporated instruction (the authoritative plan file already had all six points correctly reflected), and simply re-confirmed via `ExitPlanMode` without additional changes.
   - **Stale project-committed plan snapshot** (`ai/plans/011_brand-icons-notice-promo-polish-and-relative-time-display.md`) — discovered via `git status`/`git diff` to be out of sync with the authoritative `/home/user/.claude/plans/fluttering-growing-bumblebee.md` (still had first-draft content plus one stray uncommitted typo edit). This was being actively fixed (reading both files to prepare a sync) when the conversation was cut off for this summary — **not yet resolved**.
   - No code-level errors yet since no implementation code has been written in this segment.

5. Problem Solving:
   - Solved "which icon package actually has the needed brand marks" through direct, repeated empirical verification (unzipping wheels, installing in throwaway venvs, enumerating constants) rather than trusting package names/descriptions at face value — caught two consecutive wrong assumptions (`fontawesomefree` lacking brands entirely; `fontawesome-free-pack` lacking Copilot specifically, contradicting the user's stated belief) before they could propagate into broken implementation.
   - Solved the "structured icon addressing" requirement by recognizing the frontend `<Icon>` component's props (`source`/`family`/`version`/`icon`) already naturally mapped onto the requested `pack`/`set`/`version`/`name` four-dimension structure from the very first draft — only the backend-side representation needed to become a real `NamedTuple` (`IconRef`) instead of implicit dict/string mappings.
   - Ongoing/not-yet-resolved: syncing the stale `ai/plans/011_...md` git-tracked snapshot to match the authoritative plan content (in progress, interrupted mid-fix).
   - Not yet started: any actual Cluster 1-7 implementation code.

6. All user messages:
   - `/plan` command (long, itemized, this is the full original multi-part request — preserved verbatim in section 1 above) — the icon endpoint, past-window `(<1m)` bug, markdown+position+overflow+page-banner for notes, ServicePanels relative time, and filter-chip icons request.
   - `AskUserQuestion` answer: `"Use \`fontawesome-free-pack\` then, that's up to date."` (resolving the fontawesomefree→replacement-package question).
   - A tool-result-interrupt style user turn containing the corrective `/plan` command (verbatim, preserved in section 1): "Plan changes: - Change the svg URL to `fontawesome-free-pack` then, to keep it straight forward. - Brands `copilot` should be included since v`7.3.0`. Either way it should be added to `SERVICE_ICON_SLUGS`. - Feel free to extract the chip as component for better reuse. - Yeah, I want provider icons too, so that's why I was thinking about maybe putting those inside the `class` definition as static constant. - you can go ahead and select those icons already from the available free icons. - with now needing brand and free, therefore pack, version, set, name should be defined properly, instead of just the name, so others can be used in the future. - Use a proper markdown dependency to be future proof - the observed data is not under my control. - Make sure to escape if using raw HTML."
   - `AskUserQuestion` answer: `"Use GitHub's icon as a stand-in."` (resolving the re-verified Copilot-doesn't-exist finding).
   - A second, apparently duplicate `/plan` command with identical-looking corrective content (treated as a stray re-delivery, not a new instruction, after verification via `git diff`) — no distinct new content beyond what was already the same six bullet points already incorporated.

7. Pending Tasks:
   - Cluster 1 (task #6, `[pending]`): backend icon-serving endpoint — `pyproject.toml` dependency, new `src/ai_usage/icons.py` (`IconRef` + resolver), two new routes in `src/ai_usage/api.py` (versioned + latest-redirect), tests in `tests/test_api.py`.
   - Cluster 2 (task #7, `[pending]`): frontend `Icon.vue` component.
   - Cluster 3 (task #8, `[pending]`): `SERVICE_ICONS` in `graph.py`, `Provider.icon` class attribute set per subclass, catalog API `service_icons`/`provider_icons` fields, frontend `types.ts`/`App.vue` wiring.
   - Cluster 4 (not yet task-tracked): extract reusable `Chip.vue` component, refactor `App.vue`'s 4 chip-group blocks to use it.
   - Cluster 5 (not yet task-tracked): add `markdown-it` dependency, `renderNoteMarkdown()` helper, reorder notes to top of `axisTooltipHtml`, add `extraCssText` to fix tooltip overflow, update `chart.test.ts`.
   - Cluster 6 (not yet task-tracked): page-level "active promos" banner in `App.vue` + `.banner-info` CSS in `main.scss`.
   - Cluster 7 (not yet task-tracked): `formatRelative()` in `time.ts`, update `windowDetailLines` to emit `<span title>` relative+absolute, update `chart.test.ts`.
   - **Not yet clarified/possibly missing from the final plan**: the user's original bullet "resets of windows in the past show `(<1m)`" (a bug about past-window countdowns) does not have an explicit fix described in any of the 7 clusters — worth confirming whether this was meant to be folded into Cluster 7 (relative time) or Cluster 5, or needs its own fix, before considering the overall request complete.
   - Sync the stale `ai/plans/011_brand-icons-notice-promo-polish-and-relative-time-display.md` (git-tracked) to match the authoritative `/home/user/.claude/plans/fluttering-growing-bumblebee.md` content — in progress, interrupted.
   - Per lplp style (active all session): commit each cluster separately once implemented, following the `ai/git/pending-commit.md` → commit `-F` workflow, folding any `ai:`-prefixed auto-commits.

8. Current Work:
   Immediately before this summary request, I was in the middle of reconciling the stale, git-tracked plan snapshot file `ai/plans/011_brand-icons-notice-promo-polish-and-relative-time-display.md` with the authoritative, currently-approved plan at `/home/user/.claude/plans/fluttering-growing-bumblebee.md`. I had:
   1. Run `diff /home/user/.claude/plans/fluttering-growing-bumblebee.md "ai/plans/011_...md" | head -5` and confirmed they differ substantially (the git-tracked one is stale/first-draft).
   2. `Read` the first 5 lines of the stale `ai/plans/011_...md` file (confirming it still says "Follow-up round of dashboard polish, six requests bundled together..." — the old context paragraph, not the corrected one).
   3. `Read` the full current content (106 lines) of the authoritative `/home/user/.claude/plans/fluttering-growing-bumblebee.md` file to have it in-hand for the sync-write.
   No write/edit had yet been made to reconcile the two files, and no Cluster 1-7 implementation work had begun.

9. Optional Next Step:
   The direct next step, continuing exactly where I left off: write the authoritative plan content (already read in full) into `ai/plans/011_brand-icons-notice-promo-polish-and-relative-time-display.md` to fix the stale/corrupted git-tracked snapshot, matching my own immediately-preceding stated intent: "syncing this file to match my ACTUAL final plan content, not leave it as a stale/corrupted first draft" and "Confirmed it's the stale first draft. Syncing." After that sync, proceed to actual implementation starting with **Cluster 1 — backend icon-serving endpoint** (task #6), per the approved plan: add `fontawesome-free-pack` to `pyproject.toml`, create `src/ai_usage/icons.py` with the `IconRef` NamedTuple and a `get_icon` resolver wrapper, add the two new `@app.get(...)` routes to `src/ai_usage/api.py` above the SPA catch-all block, add tests to `tests/test_api.py`, run `uv run pytest`/`ruff check`, then commit per lplp style before moving to Cluster 2. Before starting heavy implementation, it may also be worth a quick clarifying check with the user about the unaddressed "past-window resets show `(<1m)`" bug from their original request, since it doesn't appear in any of the 7 approved clusters.
</summary>