## Findings

### 1. Notes/promo rendering in the tooltip — markdown is real, unsanitized, unrendered

- `noteTooltipHtml` (frontend/src/chart.ts:166-170) interpolates `note.text` raw into HTML: `` `<strong>${note.text}</strong>` ``. No escaping, no markdown parsing.
- `activeNotesAt` (frontend/src/chart.ts:207-213) filters notes active at a timestamp; `axisTooltipHtml` (frontend/src/chart.ts:253-298) calls it at line 296 and appends the resulting note lines **last**, after the timestamp header and all account/provider blocks (line 297: `[header, ...blocks, ...noteLines].join("<br/>")`).
- `NoteRange.text` (frontend/src/types.ts:81-87) is just `string`, sourced via `fetchNotes()` (frontend/src/api.ts:26-28) hitting `/api/v1/notes`, which is backed by `collect_note_ranges()` in src/ai_usage/notes.py:36-75 replaying raw `text` from stored transition JSONL — no cleaning happens anywhere in that path.
- Backend producers confirm literal markdown reaches `text`:
  - `extract_claude_web_notes()` (src/ai_usage/providers/claude.py:61-73) pulls `text` straight out of GrowthBook's `defaultValue["en-US"]` with zero transformation. The pinned test fixture at tests/test_providers.py:211-226 proves this literally contains markdown: `"**Your limits are boosted.** Weekly limit is 50% higher."` → expected output unchanged, i.e. `**bold**` markdown syntax is expected to flow through verbatim.
  - `extract_claude_notes()` (src/ai_usage/providers/claude.py:46-49) and `extract_codex_notes()` (src/ai_usage/providers/codex.py:51-53) extract raw CLI-output substrings via regex (`PROMO_PATTERN`, `NOTE_PATTERN`) — these come from terminal text, not markdown, but nothing prevents markdown-like characters if a CLI ever emits them.
- **No markdown library exists.** frontend/package.json has no `marked`, `markdown-it`, `dompurify`, or any sanitizer — only `echarts`, `vue`, `vue-router`, `@sentry/vue` as deps (checked full `dependencies`/`devDependencies` list).
- **No sanitization anywhere before `v-html`.** The only `v-html` usage in the whole frontend is frontend/src/components/ServicePanels.vue:62 (`<p v-html="statsHtml(entry)" />`), which renders `windowTooltipHtml(...)` output — built from internally-controlled strings (dates, numbers), not user/promo text. The ECharts tooltip itself (using `noteTooltipHtml`/`axisTooltipHtml`) is rendered by ECharts' own tooltip `formatter` (frontend/src/chart.ts:430), which ECharts internally injects as innerHTML — same unsanitized-HTML risk, just not via Vue's `v-html` directive.

Conclusion: today, `**bold**` literal asterisks would render as literal asterisks in the tooltip (wrapped in a `<strong>` tag that already bolds the whole note text) — no markdown parsing occurs, and there's no injected sanitizer to worry about breaking. Adding a markdown renderer will need to add both a markdown lib and manual sanitization (no dompurify present).

### 2. Tooltip overflow/bounds

- `chartOption()`'s tooltip config: frontend/src/chart.ts:424-431:
```ts
tooltip: {
  trigger: "axis",
  confine: true,
  backgroundColor: dark ? "#1f2937" : "#ffffff",
  borderColor: dark ? "#374151" : "#e5e7eb",
  textStyle: { color: dark ? "#e5e7eb" : "#1f2937" },
  formatter: (raw) => ...
}
```
- `confine: true` makes ECharts clamp/reposition the tooltip's bounding box so it never overflows the chart container — but it does this by *shifting position*, not by wrapping/scrolling long content; extremely tall content (e.g. many stacked note lines) can still get visually squeezed/clipped against the container edge since ECharts doesn't auto-shrink font size or add scroll, it just repositions to the best-fit corner.
- No max-width/max-height CSS is set anywhere for the tooltip. frontend/src/components/UsageChart.vue has no tooltip-specific CSS at all (only a comment at line 25 noting `chartOption()` already themes everything); frontend/src/styles/main.scss also has no tooltip selectors (only `.banner`, `.banner-error`, `.toolbar`, etc. — see below). So a long note (especially unbounded markdown/links) has no width/height ceiling other than `confine`'s repositioning behavior — a real overflow-clipping risk when notes are added at the top of a potentially-already-tall multi-series tooltip.

### 3. Page-level banner reuse

- frontend/src/App.vue: `notes` ref declared at line 12, populated by `loadNotes()` (lines 120-122) which calls `fetchNotes()`, invoked in `onMounted` (line 154) and again on every SSE `"sample"` event (line 160). Currently `notes` is **only** consumed by `<UsageChart :notes="notes" ... />` (line 276) — there is no other place notes are surfaces at the page level.
- Existing banner precedent: frontend/src/App.vue:179
```html
<p v-if="exposed" class="banner banner-error">This dashboard is exposed without authentication.</p>
```
placed directly under the `<header>`, driven by the `exposed` computed const (line 27).
- CSS for `.banner`/`.banner-error` lives in frontend/src/styles/main.scss:112-123:
```scss
.banner {
  max-width: 1500px;
  margin: 0 auto 1rem;
  padding: .7rem 1rem;
  border-radius: .75rem;
  font-weight: 600;
}
.banner-error {
  background: var(--color-error);
  color: var(--color-error-text);
}
```
  (and a dark-mode variant tweak at main.scss:227, `&.banner-error { color: var(--color-error-text); }`, inside what's presumably a `.dark` block — worth reading a few lines above 227 if exact dark selector context matters for a new banner variant).
- A new "active promos" banner can reuse `.banner` (base class) with a new modifier class (e.g. `.banner-info`/`.banner-promo`) following the exact same pattern as `banner-error`, rendered similarly with `v-if`/`v-for` over `notes.value` filtered to "currently active" (same predicate as `activeNotesAt` in chart.ts, evaluated at `Date.now()`), placed right after or before the existing exposed-warning `<p>`.

### 4. ServicePanels.vue time display

Full file read (frontend/src/components/ServicePanels.vue, 128 lines). It does **not** call `windowTooltipHtml`/`pointTooltipHtml` from chart.ts directly inline for each field — it calls `windowTooltipHtml` once per metric via `statsHtml()`:
```ts
function statsHtml(entry: PanelEntry): string {
  if (!entry.window) return "No window data yet.";
  return windowTooltipHtml(entry.item, entry.window, new Date(), props.accountLabels, false);
}
```
(lines 50-53), rendered via `<p v-html="statsHtml(entry)" />` (line 62). So all the absolute-time strings shown in ServicePanels actually come from inside `windowTooltipHtml`/`windowDetailLines` in chart.ts, not from ServicePanels.vue itself:
- frontend/src/chart.ts:130 — `` `${new Date(window.start).toLocaleString()} → ${new Date(window.end).toLocaleString()}` `` (window start/end)
- frontend/src/chart.ts:147 — `` `At this rate, you'll hit 100% around ${exhaustedAt.toLocaleString()}` `` (projected exhaustion time)
- (For completeness, `pointTooltipHtml` at chart.ts:111 and chart.ts:120 also uses `.toLocaleString()` for point time / window end, though that function is used by the ECharts tooltip via `axisTooltipHtml`'s callers, not directly referenced in ServicePanels.vue — need to double check: grep shows ServicePanels only imports `windowTooltipHtml`, not `pointTooltipHtml`.)

All of these are absolute `.toLocaleString()` calls, no relative time anywhere.

- frontend/src/time.ts has **no** relative-time helper: grepping for "ago", "in ", "relative" in that file returns nothing. The only duration-related helper is `formatDuration(ms)` (frontend/src/time.ts:80-90), which formats a signed duration in ms as `"2h 32m"`/`"3d 4h"`/`"<1m"` (already handles negative durations with a leading `-`, two largest non-zero units). This is directly adjacent/reusable for a "X ago"/"in X" relative-time helper — e.g. `formatDuration(Date.now() - t)` plus a suffix decision (`ago` vs `in`) based on sign, since `formatDuration` already strips the sign into its own `-` prefix rather than words. A new helper (e.g. `formatRelative(date, now)`) would need to be added, likely wrapping `formatDuration` and adding `"ago"`/`"in "` and probably an accompanying `title=` (absolute-time tooltip) since the plan wants relative display with absolute tooltip.

### 5. Existing test coverage

- frontend/src/chart.test.ts:
  - Notes marker series test ("adds a notes marker series only when notes are present"), lines ~101-120.
  - `describe("noteTooltipHtml", ...)` block, lines 122-141: pins current `<strong>${note.text}</strong>` + range format for both open-ended and closed ranges — **this test will need updating/extending** once markdown rendering changes `noteTooltipHtml`'s output.
  - `describe("axisTooltipHtml", ...)` block, lines 310-380: includes "appends any active note once, not per series" (line 361-372ish) pinning that notes appear once at the end after all series blocks — confirms today's ordering (notes last) is intentionally tested, so moving notes to the top of the tooltip will need this test rewritten, not just extended.
  - No test currently checks tooltip HTML length/overflow or `confine` behavior (that's an ECharts runtime behavior, not unit-testable in this file easily).
- **No dedicated ServicePanels test file exists** (`find` for `*servicepanel*` in frontend/src only found the component itself, no `.test.ts`/`.spec.ts` companion). So there is zero existing pinned behavior for ServicePanels.vue's date rendering — a new relative-time feature there is greenfield from a testing perspective, aside from whatever `windowTooltipHtml`/`windowDetailLines` tests exist in chart.test.ts already covering the strings it reuses.