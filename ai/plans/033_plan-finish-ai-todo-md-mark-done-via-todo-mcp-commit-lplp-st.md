# Plan: finish ai/todo.md, mark done via todo MCP, commit lplp-style

## Context
Only one open item in `ai/todo.md` (line 18): *"each increasing datapoint of a graph still draws its own max-square on top of last point's max square"* (`todo:382d222f-3a08-4431-b907-b71d477702b7`, calendar 7, follow-up to the layering todo).

Findings:
- Frontend (`frontend/src/chart.ts:525-541`) draws exactly one markArea per `GraphWindow` (oldest-first layering already done in 5be87c5). So the duplication must come from the backend emitting many windows.
- Backend cause was sub-second jitter of `reset_at` (e.g. 04:49:59.868 vs 04:50:00.410) making every sample its own window in `build_windows()` (`src/ai_usage/graph.py:271`). Commit 8fffb0a already added `canonical_reset_times()` (60s tolerance) – it is in HEAD.
- Evidence the symptom the user sees is a stale server: the live instance on :4458 is the uv-installed tool (`~/.local/share/uv/tools/ai-usage`, started before 8fffb0a) and `/api/v1/series` still returns 1184 windows for 2676 five-hour points, all with identical (second-truncated) bounds and differing maxima. Real history files are clean (one source, sub-second jitter only, 27 reset clusters in 13 days).

## Steps
0. **Fix `scripts/run.sh` (user request):** the working-tree edit renamed `project_dir` to a typo `project_dirt`, so `cd "${project_dir}"` is empty. Derive `project_dir` from the script location (`$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)`), dropping the hardcoded paths. In `do_run`: `cd "${project_dir}"`, build frontend (`corepack yarn@4.9.2 build`, output `frontend/dist` is force-included in the wheel per `pyproject.toml:55`), then `uv tool install --reinstall .` (so the installed tool picks up backend + fresh frontend; this is what was stale), then `ai-usage up`. Fail the iteration on build/install errors instead of starting an old install. Update the README line ~242 description accordingly. Not testable interactively (no tty) – verify with `bash -n scripts/run.sh` and a non-tty run of the build+install steps only.
1. **Verify against current code (not the stale install):** run `build_series()`/`build_windows()` from the repo (`uv run python -I`-style script in scratchpad) on the real `~/.ai-usage/history` samples for 2026-10-06..14; expect ~1 window per reset cluster (≈27 five-hour, 2 seven-day). Also run `uv run pytest tests/test_graph.py`.
2. **If counts are correct:** no code change needed beyond a regression test if one is missing — add to `tests/test_graph.py` a case with *increasing* percentages + jittered `reset_at` asserting a single window whose `maximum_percentage` is the max (check existing test added in 8fffb0a first; reuse its helper). Tell the user the running instance must be restarted/reinstalled (`uv tool install --reinstall .` or the repo's `scripts/run.sh`) to pick up the fix.
3. **If counts are still wrong:** inspect what differs between windows (unrounded `start`/`end`, `window_seconds`, `split_on_reset_drops` at `RESET_DROP_THRESHOLD_PCT`), fix in `graph.py` (cluster key / grouping), add a failing-then-passing test, and run the focused frontend tests from CLAUDE.md (`corepack yarn@4.9.2 run test --run src/chart.test.ts src/components/UsageChart.test.ts`, `... run type-check` in `frontend/`).
4. **Check & mark done:** tick line 18 in `ai/todo.md` (`- [x]` + `_(done)_`), then call `mcp__sync_todo__complete_todo(calendar_id=7, uid="382d222f-3a08-4431-b907-b71d477702b7")` (load the tool via ToolSearch first). Lines 1-3 and the other items are already ticked.
5. **Commit:** invoke the `commit-with-lplp-style` skill; message via `ai/git/pending-commit.md`; stage only files for this task (do NOT include the pre-existing unrelated `ai/query.md` / `scripts/run.sh` modifications); fold nearby `ai:` auto-commits per the skill; include the required Co-Authored-By / Claude-Session trailers.

## Verification
- Script from step 1 shows window count ≈ reset-cluster count with current code.
- `uv run pytest tests/test_graph.py` green; frontend focused tests + type-check green if touched.
- Todo MCP call returns success; `ai/todo.md` line 18 ticked.
