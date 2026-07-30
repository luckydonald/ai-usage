Research task, no code changes. I need to plan a feature: detect quota window resets (substantial usage drop, e.g. from ~100% down to low %, ignoring small <2% caching noise drops) and stop/split the "window" rendering in the graph instead of continuing it as one window, plus handle the "100% black overlay" so it doesn't keep blocking view after a reset.

Read and report on:
1. src/ai_usage/models.py - GraphPoint, GraphSeries, GraphWindow definitions (fields, what "window" means here, how window boundaries/start-end are currently determined, any existing gray/100% overlay concept fields)
2. src/ai_usage/graph.py - build_series(), how it builds windows from stored samples, how current/maximum/unit preserved, whether there's already reset detection logic, how it groups samples into windows currently (time-based? provider-reported window id?)
3. frontend/src/types.ts - TS mirror of GraphWindow/GraphPoint/GraphSeries
4. frontend/src/chart.ts - buildAxisTooltipGroups(), axisTooltipData(), axisTooltipHtml(), and specifically how the "gray/100%" overlay area is rendered (search for terms like "100", "full", "gray", "block", "maximum", "window")
5. Any DB schema/storage files relevant to how samples/windows are persisted (search for relevant models/schema, e.g. src/ai_usage/db.py or similar, migrations directory)
6. Search for existing "window" reset/rollover handling anywhere in codebase (grep for "reset", "rollover", "new window", "refresh")

Report back (under 500 words):
- Where window boundaries are currently determined (DB-side vs frontend-side)
- Where/how the gray 100%-full overlay is computed and rendered
- What data model changes (if any minimal) would be needed to mark a window as "closed"/"reset" at a point, both DB-side and API-contract-side
- Whether percentage/current/maximum data is per-sample (so a frontend threshold-drop detection is feasible) or aggregated
- Any prior art/comments in the code about caching noise or drop tolerance (the codebase apparently already tolerates <2% drops somewhere per user)
