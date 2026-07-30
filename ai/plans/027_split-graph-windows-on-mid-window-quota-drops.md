# Split graph windows on mid-window quota drops

## Context

Some providers bump a quota mid-window (e.g. Copilot: 5000/5000 credits spent = 100%, refreshed to
7500/7000 total → next sample reads 5032/7000 = 71.9%) without changing `reset_at`/`window_seconds`.
`build_windows()` in `src/ai_usage/graph.py` currently groups samples purely by the tuple
`(reset_at, window_seconds)`, so this whole span stays *one* `GraphWindow`. Two problems fall out
of that:

1. `exhausted_from` is set to the timestamp of the *first* sample that hit ≥100% in the group and
   never re-checked — so the gray "exhausted" overlay in `frontend/src/chart.ts` keeps covering the
   chart all the way to `window.end`, even after the quota bump made the window no longer full.
2. The window is drawn as one continuous span through an actual quota reset, which is misleading —
   it should render like a new window opened, matching how a real provider-reported reset already
   looks.

Small drops (~<2%) are known API-response caching noise (observed consistently, e.g. from Codex) and
must NOT trigger a split — only substantial drops indicate a genuine reset/bump.

Confirmed via `frontend/src/chart.ts:75-90,535-545`: the gray-overlay band and all window-stat
calculations key off each individual `GraphWindow`'s own `start`/`end`/`exhausted_from`. If the
backend emits two windows instead of one at the drop point, the frontend already renders correctly
with **no changes needed** — this is a backend-only fix.

## Approach

Split window grouping in `src/ai_usage/graph.py`: after grouping samples by
`(reset_at, window_seconds)` as today, further split each group into segments wherever consecutive
samples (sorted by `observed_at`) show `percentage` dropping by more than a threshold (e.g. 2
percentage points). Each segment becomes its own `GraphWindow`, computed as if it were an
independently-grouped window today (own `maximum_percentage`, own `exhausted_from`, own
`projected_end_percentage`).

### Segment boundaries

- For a group's samples, walk them in order; start a new segment whenever
  `curr.percentage < prev.percentage - RESET_DROP_THRESHOLD_PCT` (constant, e.g. `2.0`).
- Closing (non-last) segment's `end` = the *next* segment's first sample's `observed_at` (the very
  point where the drop was observed) — mirrors how a real reset's `end` equals the next window's
  `start`. This also means `with_window_reset_zeros()` won't spuriously inject a synthetic 0% point
  there, since that timestamp already has a real point in `points` (the check
  `window.end not in existing_timestamps` already guards this — no change needed there).
- Next segment's `start` = that same timestamp.
- Only the **last** segment of a group can be `current` (`end > now`, using the group's real
  `reset_at`/`last_at` as before). Earlier segments (closed by a detected drop) are always
  `current=False`.
- `exhausted_from` / `maximum_percentage` / `projected_end_percentage` computed per-segment from
  only that segment's samples (fixes the stale-gray-overlay bug directly).
- First segment's `start` keeps today's logic (`reset_at - window_seconds` or first sample's time).

### Files to change

- `src/ai_usage/graph.py`: refactor `build_windows()` — add a segment-splitting step before
  building each `GraphWindow`, and a `RESET_DROP_THRESHOLD_PCT = 2.0` module constant. Reuse
  existing helpers (`aware()`, `projected_percentage()`) per segment instead of per whole group.
- No changes needed to `src/ai_usage/models.py`, `frontend/src/types.ts`, `frontend/src/chart.ts`,
  or any storage/ORM/migration — the `GraphWindow` contract shape is unchanged, just more instances
  of it are produced from the same input samples.

### Tests

- `tests/test_graph.py` (existing `build_windows`/`exhausted_from` coverage around line 27/145):
  add cases for
  - a mid-group percentage drop >2% with unchanged `reset_at` → asserts two `GraphWindow`s, correct
    `start`/`end` at the split point, `current=False` on the first and `current` reflecting real
    state on the second, and `exhausted_from` not leaking from the first segment into the second.
  - a small drop (e.g. 1%) → asserts still one window (noise tolerance holds).
  - the existing 100%-exhausted-then-recovers-lower scenario → gray overlay data
    (`exhausted_from`) no longer spans past the split.

## Verification

- Run `uv run pytest tests/test_graph.py` (adjust to project's actual test runner if different —
  check `pyproject.toml`/`Makefile`) and confirm new + existing cases pass.
- Optionally sanity-check with the dev frontend (port 4458) using a crafted sample set reproducing
  the Copilot 100%→71.9% scenario, confirming the gray band stops at the split and a fresh window
  visually begins — per `[[feedback_ground_ui_wording_via_screenshot]]` habit, but this is a
  backend-only data change so a screenshot isn't strictly required to validate correctness.
