# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Other projects using this _base_ are expected to overwrite this file.**

If the primary working directory (visible in the system prompt) ends with `/base`, read `ai/°base/AGENTS.md` for full codebase guidance.

## Dashboard graph edits

For graph hover or click-overlay work, trace the whole data and rendering path before editing:

- `src/ai_usage/models.py` defines the graph API contracts (`GraphPoint`, `GraphSeries`, and `GraphWindow`).
- `src/ai_usage/graph.py` turns stored samples into those contracts. `build_series()` is where source-native values such as `current`, `maximum`, and `unit` must be preserved.
- `frontend/src/types.ts` mirrors the API contracts in TypeScript.
- `frontend/src/chart.ts` builds the ECharts options and tooltip data. `buildAxisTooltipGroups()` creates the shared tooltip rows, `axisTooltipData()` is the pinned-overlay contract, and `axisTooltipHtml()` is the ECharts HTML counterpart. Keep the latter two sourced from the same data.
- `frontend/src/components/UsageChart.vue` renders the click-pinned overlay; `pinTooltip()` opens it. Use the shared `Icon` component for Font Awesome icons; it resolves the project icon endpoint.
- Focused coverage lives in `frontend/src/chart.test.ts` and `frontend/src/components/UsageChart.test.ts`. Run `corepack yarn@4.9.2 run test --run src/chart.test.ts src/components/UsageChart.test.ts` and `corepack yarn@4.9.2 run type-check` from `frontend/`.
