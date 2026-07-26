---
name: feedback_vue_no_raw_html_strings
description: "In this Vue frontend, build UI with real components, not string-concatenated HTML — even for complex tooltip content"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: c77b952d-3d3d-4f06-9630-bdd4829adc23
  modified: 2026-07-26T22:30:40.523Z
---

Don't build markup by string-concatenating HTML (`<span style="...">...</span>` joined into one big string) in a `.ts` helper and injecting it via `v-html`. Use real Vue components (`<Icon>`, `<Badge>`, etc.) in the template instead, even when the content is complex (icons + colored badges + multi-line grouped data).

**Why:** User explicitly corrected this after I built the chart hover/click tooltip content as HTML strings in `chart.ts` (`badgeHtml()`/`iconHtml()`/string-join) and injected the result via `v-html` in `UsageChart.vue`. Message: "Don't use raw HTML, therefore edit to use a component. This is Vue."

**How to apply:** When a data-shape is genuinely reusable across two render targets (e.g. this app's ECharts-native hover tooltip *and* a Vue-rendered pinned/click dialog), split a pure-data builder (returns plain objects, e.g. `axisTooltipData()`) from a presentation layer. Keep the HTML-string renderer *only* where a non-Vue-controlled surface truly requires a string (ECharts' own tooltip `formatter` sets `innerHTML` on a DOM node it manages itself — no way to mount a Vue component into it). Everywhere the DOM is actually Vue's own template (dialogs, panels, overlays), render with components, never `v-html`-of-a-built-string.

Exception that's fine to keep: `v-html="renderNoteMarkdown(text)"` for rendering actual markdown-formatted user/note text — that's rendering *content formatting*, not building UI structure, and matches an established pattern already used elsewhere in the app (`App.vue`'s note banners). Don't conflate the two when reviewing future `v-html` uses.

See also [[project_ai_usage_icon_infrastructure]].
