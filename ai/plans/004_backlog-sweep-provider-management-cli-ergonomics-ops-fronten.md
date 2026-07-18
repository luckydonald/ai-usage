# Backlog sweep: provider management, CLI ergonomics, ops, frontend chart UX

## Context

User dropped a ~20-item backlog covering provider/account data-management gaps, CLI ergonomics/reliability, server ops, and frontend chart UX. Grouped into phases so each is independently reviewable/testable rather than one giant change. Grounded in exploration of `src/ai_usage/*` and `frontend/src/*` (see file:line refs below).

One item is already done: **yarn@4/berry** — `frontend/package.json` already has `"packageManager": "yarn@4.9.2"`, `.yarnrc.yml`, `.yarn/`, and only `yarn.lock` present. No action needed; will just confirm/report.

---

## Phase A — Provider/account data lifecycle (backend)

**A1. `provider merge <A> <B>`** — new CLI command merging account A's history into B, then deleting A.
- Reuse `resolve_account`/interactive picker pattern from existing `provider` subcommands (cli.py, `resolve_account` ~466-520) for selecting both A and B.
- Merge steps: `UPDATE metric_sample/fetch_run SET account_id=B WHERE account_id=A` (orm.py); for `crawl_state` (PK is account_id) — delete A's row (or upsert-merge fields like `failure_count`/interval, keep B's) since B's own row already exists.
- Move on-disk JSONL tree `history/v1/{service}/{A}/...` → `.../{B}/...` (history.py `event_path` convention), then update `indexed_file.path` rows to match new paths.
- Delete A's `services/{service}/{A}.yml` config file and `CredentialRecord` (respect existing `provider remove` deletion path, cli.py ~684-692).
- **A2. `provider rename`** (aliases `name`, `mv`) — same resolve_account/positional-args shape as existing subcommands; renames just the account's display `name` field (`AccountConfig.name`), no data movement. Simple, no schema change.

**A3. Multi-computer host allow/deny list** — keep `AccountConfig.enabled: bool` as-is (global "is this account tracked at all" switch), and add a *shared*, git-synced `hosts: list[tuple[str, str]] | None = None` field (`(hostname, host_id)` pairs, `host_id` a UUIDv7 — not hostname alone, since hostnames aren't trusted to be unique). `None`/empty = no restriction (crawl on every machine, today's behavior). Non-empty = only crawl on machines whose local `host_id` matches an entry.

- **Local host identity file**: new `local/host_id.json` (or similar, under the existing gitignored `local/` convention) storing `{hostname: str, host_id: <uuid7>}` for *this* machine. Written once, read on every startup.
- **Resolution on startup** (`Paths.ensure()` or a new `resolve_host_identity()` called early in `run_all`/`serve`/crawl paths):
  1. **Local file missing** (fresh checkout/install):
     - Scan all configured accounts' `hosts` lists for entries whose `hostname == socket.gethostname()`.
     - **Exactly one match** → ask to restore that `(hostname, host_id)` as this machine's identity (AskUserQuestion-equivalent in TUI context, i.e. the existing interactive-picker pattern from `provider_tui.py`; a yes/no confirm).
     - **Multiple matches** (same hostname string appears under different `host_id`s across accounts — genuinely ambiguous) → TUI: prompt which one to adopt, with an explicit "none, generate new" option. Non-interactive (no tty / `--no-input`): hard error pointing at the missing `local/host_id.json` path and explaining what it's for and how to pick/create it interactively.
     - **No matches** → generate a new UUIDv7, write `local/host_id.json`, proceed.
  2. **Local file exists** → just use it, no scanning/prompting.
- **Enforcement**: crawler/collector checks, for each account with non-empty `hosts`, whether this machine's `host_id` is in the list before fetching; skip (not error) otherwise.
- **Adding a machine to an account's `hosts` list — decided: both paths exist:**
  - **A3a. Manual command**: `provider hosts add|remove` (with common aliases, matching existing subcommand alias style e.g. `ls`/`list`), same `resolve_account` selection pattern as other `provider` subcommands, explicit add/remove of `(hostname, host_id)` entries.
  - **A3b. First-crawl wizard** (interactive only; non-interactive → error with explanation of what's missing and how to fix it): triggered when this machine's `host_id` matches **no** account's `hosts` list for **any** configured service (the "first crawl on this machine" condition). Root menu, always these choices (label/subtext varies per state):
    1. **Enable existing service on this device** — submenu listing every configured service: `« back`, `service 1`, `service 2`, … Selecting a service adds this machine's `(hostname, host_id)` to that account's `hosts` list, then returns to the root menu (so multiple services can be enabled in one pass).
    2. **Create new** — runs the `provider add` wizard (existing interactive flow), with a `« back` before it starts; returns to the root menu once done.
    3. **Done: finish and resume {crawl/serve/…}** — exits the wizard, resuming whatever operation triggered it (crawl/serve/etc — label fills in the actual caller). If nothing is configured on this machine yet at exit, labeled **Exit** instead, subtext "exit without creating/selecting any service". Root menu is a plain 3-option menu throughout (no special-casing option count).
  - Both A3a and A3b write into the same `hosts` field on the shared account yaml (synced via D2), so either path is visible to all machines after the next sync.

## Phase B — CLI/config hygiene

**B1. UUIDv7** — replace bare `uuid.uuid4()` calls (config.py:90, database.py:66/75, collector.py:47) with UUIDv7 (time-ordered). No stdlib UUIDv7 in this Python version — add `uuid6`/`uuid_utils` dep or a small local helper. New IDs only; no backfill of existing v4 ids needed (don't need to be one type).

**B2. `credential.key` under `local/`** — move `Paths.credential_key` (settings.py:35) from `root/credential.key` to `root/local/credential.key`, so `.gitignore` only needs `/local/` (drop the separate `/credential.key` line, settings.py:46-48). One-time migration: if old `root/credential.key` exists and new path doesn't, move it on `Paths.ensure()`.

**B3. CLI help text truncation** — root cause per exploration: click's `HelpFormatter` wraps at `shutil.get_terminal_size()` width, defaulting to 80 cols when not a tty. Fix: set `context_settings={"max_content_width": 120}` on the top-level `main` group (cli.py:194) so `--help` isn't narrow-wrapped/truncated regardless of terminal detection.

**B4. `ai-usage` bare invocation** — decided: drop the `invoke_without_command`/auto-`run_all` (cli.py:198-199). Bare `ai-usage` prints help/command list **plus a short status line** above it (account count, last crawl time) — read via `ConfigStore`/`Database` without starting the server/crawler, then `click.echo(context.get_help())`.

**B5. Rename `run-all`** — decided: rename to **`up`**, with **`start`** as an alias (`cli.py` command decorated with both names, matching the existing alias pattern used for `new`/`add`, `ls`/`list`, etc.). Old `run-all` name dropped (early-stage project, no back-compat shim needed) unless review turns up an external script depending on it.

## Phase C — Server/ops reliability

**C1. Ctrl+C hang** — root cause: `/api/v1/events` SSE endpoint (api.py:152-173) is an infinite `while True: await asyncio.sleep(2)` loop; uvicorn's graceful shutdown waits for it to finish, and it never does, so Ctrl+C appears to hang (ai/errors/2.txt confirms). Fix: give `run_server_and_crawler` (api.py:229-253) a signal handler that cancels the `TaskGroup` on first SIGINT, and make the SSE loop check a shutdown event / catch `asyncio.CancelledError` and return promptly instead of looping forever uninterruptibly.

**C2. Port fallback** — in `serve`/`run-all` (cli.py ~876-909, api.py `run_server_and_crawler`): if port is the *default* (4458) and bind fails (`OSError`/`errno EADDRINUSE`), retry through the candidate list `6900, 6969, 6699, 8698, 8008, 8690, 8699, 8404` then `44xx`/random. If `--port` was explicitly passed, keep current behavior (hard error, no fallback) — needed for scripted startup.

**C3. Vertical "now" line prep** — n/a here, frontend item, see Phase E.

## Phase D — History cleanup & git backing

**D1. Dedup history log cleanup** — new maintenance routine (CLI command, e.g. `ai-usage history cleanup [--older-than 7d]`) that rewrites each day's JSONL file (history.py `event_path` layout) dropping consecutive lines where percentage/current/maximum are unchanged, always keeping first+last of a duplicate run. Must also: delete the now-stale `MetricSampleRecord` rows by `event_id`, and rewrite `IndexedFileRecord` byte offset/size/mtime bookkeeping (history.py ~141-150) since indexing is byte-offset based — safest approach is re-index the file from scratch after rewrite (reset the `indexed_file` row for that path) rather than trying to patch offsets.

**D2. Auto git commit/push for `~/.ai-usage`** — new opt-in setting (e.g. `git.enabled` in a top-level config, or detect `.git` present in `paths.root`). After writes to `.gitignore`/`history/`/`services/`, run `git add .gitignore history/ services/ && git commit -m "<UTC timestamp>: Updated crawl results" && git push`, debounced **10 minutes** (confirmed). On push failure (no remote, auth issue, network) — **log and skip**; the local commit still happens regardless, push is retried on the next debounce cycle, never blocks/crashes the crawl loop. Ties into D1's cleanup cadence question — D1's "older than last week (or last remote push/pull if git enabled)" retention needs to read the git log for last push time when git is enabled. Also feeds Phase A3: `services/` yaml holding `hosts` lists is exactly what gets synced here, so A3's host-list edits propagate across machines through this same mechanism.

## Phase E — Frontend chart UX

**E1. Dropdown options `auto/1h/3h/6h/12h`** — extend `TimePreset` union + `presetLabels` + `rangeForPreset` branches in `frontend/src/time.ts:1-29`; decide if `auto` participates in `wideningOrder` (time.ts:31) — likely yes, as the new default/first entry.

**E2. Incremental redraw (no full animate-in on reload)** — `UsageChart.vue:12-30` currently disposes/recreates the whole echarts instance on any series change and calls `setOption(..., true)` (no-merge). Fix: stop disposing on data-only updates; call `setOption` with merge semantics (`notMerge: false`) keyed by existing series `id`s (already present, chart.ts:9/32/45/59) so echarts diffs and only animates genuinely new/changed points. Keep dispose/recreate only for real theme (`dark`) changes.

**E3. Vertical "now" line, red dashed** — add a `markLine` (or dedicated series) in `chartOption()` (chart.ts, near existing markArea/reset-line construction ~29-55) at `x = now`, styled red.

**E4. Prediction line legend + reset-boundary fixes** — chart.ts:42-55. (a) give the projection series a `name` matching (or grouped with) the actual series' name, or explicitly hide/show it in the same `legendselectchanged` handler once E5 wires that up, so toggling a provider off hides its prediction line too. (b) clip `item.points` to the current `window` (`window.start`..`window.end`) before computing `last`, so the anchor resets when a new window begins instead of reusing a stale cross-window last point.

**E5. Legend/filter sync** — decided: **two-way sync**, keep both UIs. Add a `legendselectchanged` handler in `UsageChart.vue` that emits toggle events up to `App.vue`, mirrored into the `filters` reactive state (App.vue:15); conversely, when `filters` changes and `load()` re-fetches, the resulting series list drives the chart's legend `selected` map (echarts `legend.selected` option) so both stay consistent regardless of which UI triggered the change.

---

## Sequencing across phases

Phase A/B (backend/CLI) and Phase E (frontend) are independent — can be built in either order. A3 (host allow/deny) depends on nothing else in A but should land before/alongside D2, since D2 is the sync mechanism that makes `hosts` lists useful across machines. Phase C (ops) touches api.py, worth doing before D2 (auto-commit) since both touch the long-running server loop. Phase D1 (log dedup) is independent of D2 (auto-commit) but D1's "since last push" retention detail depends on D2 existing — so within Phase D, build D2 before D1, or scope D1's retention to "always 7 days" first and layer git-awareness in once D2 lands.

## Open questions — resolved

- B5: `run-all` → renamed to `up`, alias `start`.
- B4: bare `ai-usage` → help list + short status line.
- E5: two-way legend/filter sync (not legend-only).
- D2: 10 min debounce; push failure → log-and-skip, local commit still happens.

- A3: both a manual `provider hosts add|remove` command and an interactive first-crawl wizard (see A3a/A3b above) — no remaining open question.

## All open questions resolved.

## Verification

- Backend: `uv run pytest -q` after each phase; new tests per feature (merge/rename round-trip, UUIDv7 format, credential.key migration idempotence, port-fallback binding, history dedup keeps first/last + record counts match).
- CLI manual smoke: `uv run ai-usage --help` (check B3/B4), `uv run ai-usage provider rename ...`, `uv run ai-usage provider merge ...`, `uv run ai-usage up`/`start`.
- A3: delete `local/host_id.json`, run with an account that has a `hosts` list containing this hostname under a different `host_id` (ambiguous case) and confirm the picker/error paths; confirm a host not in the list gets skipped, not errored.
- Ops: manually start `ai-usage run-all`, send SIGINT once, confirm prompt shutdown (C1); start with port occupied, confirm fallback bind (C2).
- Frontend: `cd frontend && yarn dev`, visually check new dropdown presets, now-line, prediction-line legend toggle + window-reset behavior, and reduced redraw animation, per the "test in browser" requirement for UI changes.

## Todos

- [x] Phase A1: provider merge command
- [x] Phase A2: provider rename command
- [x] Phase A3: multi-computer host allow/deny list
- [x] Phase B1: UUIDv7 for new IDs
- [x] Phase B2: move credential.key under local/
- [x] Phase B3: fix CLI help text truncation
- [x] Phase B4: bare `ai-usage` shows help + status
- [x] Phase B5: rename run-all to up (alias start)
- [x] Phase C1: fix Ctrl+C hang
- [x] Phase C2: port fallback on default port occupied
- [x] Phase D1: history log dedup cleanup command
- [x] Phase D2: auto git commit/push for ~/.ai-usage
- [ ] Phase E1: frontend dropdown presets auto/1h/3h/6h/12h
- [ ] Phase E2: incremental chart redraw (no full reanimate)
- [ ] Phase E3: vertical red dashed "now" line
- [ ] Phase E4: prediction line legend + window-reset fixes
- [ ] Phase E5: two-way legend/filter sync
