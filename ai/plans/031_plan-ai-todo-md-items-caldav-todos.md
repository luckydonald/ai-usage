# Plan: `ai/todo.md` items + CalDAV todos

## Context
`ai/todo.md` holds 3 hand-written items plus a "From the todo list" snapshot of 2 `#aiUsage` CalDAV todos (calendar `TODO: Today`, id 7).

Two gaps in the input:
- **`ai/todos.md` does not exist.** Only `ai/todo.md` (and `ai/°base/todo.md`, which is base-repo-internal and unrelated). I assume `todos.md` was a typo.
- **The `sync_todo` MCP isn't connected in this session.** ToolSearch found no CalDAV tool. I can only plan the 2 already-synced items. A fresh pull of all calendars, and the `complete_todo` calls, need the MCP reconnected.

## Item status
| # | Todo | State |
|---|------|-------|
| 1 | Native unit in hover/click info | Done. `nativeUsageLabel` is built in `chart.ts`. |
| 2 | Graph-color badge on info panels | Open. |
| 3 | Relative + clock time in hover/click info (`[-]`) | Partly done. |
| 4 | Max-usage blocks overlap, one per data point (CalDAV `5fe337f2`) | Open. Likely a backend grouping bug. |
| 5 | Older max-usage blocks behind newer ones (CalDAV `e3074f3c`) | Open. |

## Work, in order

### A. One max-usage block per window (item 4). Do first, since item 5 depends on it.
1. **Diagnose against real data.** `build_windows()` in `src/ai_usage/graph.py:248` groups samples by `(aware(reset_at), window_seconds)`. If `reset_at` jitters slightly per sample, or is `None`, every sample becomes its own group, and so its own `GraphWindow` and its own markArea. Overlapping 0.16-opacity boxes of growing height would explain the gradient. Exactly 100% would be fully opaque. Query the real DB or `/api/graph` and count windows per series versus samples.
2. **Fix in `build_windows()`.**
   - Cluster `reset_at` values by tolerance (e.g. within a minute, or round to `window_seconds`-aware precision) before grouping.
   - For `reset_at is None`, don't create one window per sample.
   - Keep `split_on_reset_drops` and `RESET_DROP_THRESHOLD_PCT` as they are.
3. **Test.** Add a `build_windows` test with jittered `reset_at` that asserts a single window. Put it next to the existing graph tests, which I will locate.
4. **Frontend safeguard.** The `markArea` in `chartOption()` (`chart.ts:522`) maps `item.windows` 1:1. No change needed if the backend is fixed. If real windows legitimately nest, handle it in B.

### B. Layering (item 5)
- In `chartOption()`, sort the markArea data oldest first, so newer ones draw on top. Keep `windowIndex` pointing at the original index, because `itemTooltipHtml` indexes `item.windows[windowIndex]`.
- Set explicit `z` on the markArea (the series' `markArea.z`) if draw order isn't enough. Check this against ECharts' behavior.
- Test in `frontend/src/chart.test.ts`: area order and `windowIndex` mapping.

### C. Info-panel color badge (item 2)
- `frontend/src/components/ServicePanels.vue:99-122` renders `.info-panel` with `.chip-badge` and `.badge-row`. It has no series color.
- Series colors come from `GraphSeries.color`, which the pinned tooltip already uses via `<Badge :color="group.color">`.
- Pass a service/account → color map into `ServicePanels` from the parent (derive it from the `series` list). Render a color dot or a colored `Badge`. Reuse `Badge.vue`; no raw HTML (see memory `feedback_vue_no_raw_html_strings`).
- Question to settle at implementation: one color per panel is ambiguous when an account's metrics have different colors. Default to the account's first series color, matching `buildAxisTooltipGroups`, which uses `firstItem.color`.
- Test in `ServicePanels.test.ts`.

### D. Relative plus clock time (item 3, remaining part)
Already in place: the per-metric `resetTiming` pair (hovered vs now) with `clock-rotate-left` and `stopwatch` icons.

Remaining: `axisTooltipData().timeLabel` (`chart.ts:394`) is only an absolute `toLocaleString()`. Change it to structured data, e.g. `{ absolute, relativeToNow }` (using `formatRelative` from `time.ts`). Render both compactly in `UsageChart.vue:163` with icons via the shared `Icon`. Keep `axisTooltipHtml()`/`seriesPointTooltipHtml` in sync, as `CLAUDE.md` requires. Check first whether `axisTooltipHtml` still exists; only `itemTooltipHtml` and `seriesPointTooltipHtml` appear in the file.

Verify the exact wording against a screenshot of the dev instance on port 4458 (memory `feedback_ground_ui_wording_via_screenshot`).

### E. Housekeeping
- Tick `[x]` in `ai/todo.md` as items finish.
- For items 4 and 5, call `mcp__sync_todo__complete_todo(calendar_id=7, uid=…)` once the MCP is reachable. The uids are in `ai/todo.md`.

## Verification
- Backend: `pytest` for the new `build_windows` test, then the full graph tests.
- Frontend, from `frontend/`:
  - `corepack yarn@4.9.2 run test --run src/chart.test.ts src/components/UsageChart.test.ts src/components/ServicePanels.test.ts`
  - `corepack yarn@4.9.2 run type-check`
- Visual: run the dev instance, screenshot the graph. Expect one translucent block per window, older ones behind newer ones, and no gradient buildup. Pin a tooltip and check the time header. Check that the info panels show the color badge.
