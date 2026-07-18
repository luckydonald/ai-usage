Research-only, no edits. Scoping a plan for frontend rework in this repo's `frontend/` (Vue app, ai-usage project).

Investigate and report back (under 500 words):
1. List all files under frontend/src (components, App.vue, types.ts, any composables/stores). Give a one-line purpose per file.
2. Find the main graph/chart component(s) — what charting lib is used (chart.js? d3? custom svg?), how are per-account/per-service colors currently assigned (grep for "color" in frontend/src — the summary mentioned `account.colors: Record<string,string>` in types.ts and an existing color scheme).
3. Find how the date-range selector currently works (e.g. presets like "last 24h/7d/30d") — is there any date-picker component or library already installed (check package.json for date-picker/calendar libs)?
4. Find where a window's usage % display would need to reset to 0% after the window's reset_at passes — i.e. where "current percentage for a window" is computed/rendered from the catalog/history data (component name, file:line). Is this computed once server-side, or client-side per render/tick?
5. Briefly describe overall App.vue structure/sections (nav, filters, graph area, settings, etc.) so a "remove everything except graphs, rebuild" plan can scope what's being torn out.

Give file:line refs. Don't propose implementation, just report current state.