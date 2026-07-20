# Implement remaining `ai/plans/pending.md` backlog

## Context
`pending.md` accumulated a large backlog. Prior sessions already implemented: live crawl/up config-reload logging, graph animation/stray-line/future-padding bugs, hover tooltips, the include-window-ends toggle, and the basic per-service info panels. This plan covers everything still open in that file. User selected all remaining clusters plus two design decisions for the account-grouping feature (persistent alias group, not one-time merge; overlapping samples resolved by max-percentage). Each cluster below is committed separately per the lplp commit-style skill, in the order listed (small/clear fixes first, riskier new subsystems last).

## Cluster A — Quick wins

**A1. `provider add` repeats already-discovered adapters in the advanced/manual section**
Root cause (confirmed via code read): `matching_providers()` (`src/ai_usage/provider_discovery.py:50-62`) returns every registered provider for a service/key with no awareness of what `discover_accounts()` already turned into a `DiscoveryChoice`. Both call sites feed it straight into the manual list:
- `src/ai_usage/cli.py:399-403` (`print_discovery_choices(..., manual_providers=matching_providers(...))`)
- `src/ai_usage/cli.py:355-364` (`select_discovered_account`, builds `manual_options` from the same unfiltered list)

Fix: at both call sites, filter `matching_providers(...)` to exclude any `(provider.service, provider.key)` already present in `{(c.service, c.provider) for c in choices}` before building the manual/advanced list.

**A2. Info panel styling (leftover items from the panels feature)**
In `frontend/src/components/ServicePanels.vue`:
- Remove `text-transform: uppercase` from the `.info-panel h2` rule (backlog: "Don't capslock the provider/account headline").
- Render the account portion of the `<h2>` as a small chip/tag element instead of plain text (e.g. wrap `panel.accountLabel` in a `<span class="account-chip">`), styled as a rounded-pill bubble consistent with the existing `.chip` styling in `frontend/src/styles/main.scss`.

## Cluster B — Claude statusline fallback + model recording

**B1. Statusline falls back to `cli-usage` when stale**
`ClaudeStatusProvider.fetch` (`src/ai_usage/providers/claude.py:344-411`) already computes relay-file age vs `stale_seconds` (default 120s, line ~352) and currently returns `FetchStatus.STALE` with the stale data when `age > stale_seconds` (~line 384). Change that branch to instead invoke `run_claude_usage(...)` (the same call `ClaudeUsageProvider`/`cli-usage` uses, `claude.py:414-428`) and return its fresh result. Keep the "missing/empty relay file" fallback path (~lines 395-402) as-is — it already does this correctly for the other case.

**B2. Record the used model with each metric**
- Add `model: str | None = None` to `Metric` (`src/ai_usage/models.py:41-58`).
- Add a matching nullable column to `MetricSampleRecord` (`src/ai_usage/orm.py:45-66`) and wire it through the SQLite upsert.
- Wire it through `history.py`'s dict-building/reload (~`history.py:176`) alongside the existing `metadata_json` handling — additive/optional field, no migration needed for existing jsonl files.
- Populate it in both providers:
  - `claude.py`: model-parsing logic already exists in `claude_metric_key()` (`claude.py:45-54`) to fold model into per-model metric keys — reuse that same extraction to also set `Metric.model` directly instead of (or alongside) folding it into the key/name.
  - `codex.py`: parse the `model: gpt-5.6-sol medium` style line from the CLI motd/status output (see `ai/references/console-output/codex/motd/normal.md:4,15`) similarly to how `STATUS_PATTERN`/`STALE_WARNING_PATTERN` (`codex.py:30-36`) already extract other fields from the same raw text.

## Cluster C — Special events / notes tracking

Goal: detect promo/limit-boost banners (Claude CLI "+50% weekly limits promo…", Codex CLI "You have N usage limit resets available…"), record only on change (not every tick), store outside the normal metric-keyed history tree, report verbosely to console, and surface historically on the graph.

**C1. Parsing**
- `claude.py`: `parse_usage_output` (`claude.py:83-99`) currently discards any line not matching `SECTION_PATTERN`. Add a separate small regex/check against the raw `/usage` output text (already available in `run_claude_usage`, `claude.py:431-459`) to extract a promo banner line like `+50% weekly limits promo through Aug 19 · clau.de/cc-50-promo`, producing a note id + human text + optional expiry date.
- `codex.py`: similarly extract the `You have N usage limit resets available. Run /usage to use one.` line alongside the existing `STALE_WARNING_PATTERN` extraction in `CodexStatusProvider.fetch` (`codex.py:419-441`).
- The Claude-web promo API mentioned in the backlog is explicitly **out of scope** — no confirmed endpoint identified yet; only the CLI-sourced notes are implemented now.

**C2. Storage — new sibling tree, change-only writes**
- New small JSON/JSONL store per `(service, account_id)`, living alongside (not inside) the existing metric-keyed history tree — e.g. `paths.local`-relative `notes/{service}/{account_id}.jsonl`, one line per state transition: `{observed_at, note_id, text, active: true|false}`.
- Diffing pattern modeled directly on `Crawler.report_account_changes()`/`report_git_backup_toggle()` (`src/ai_usage/crawler.py:48-70`): keep an in-memory "currently active note ids" set per account (loaded from the last recorded state on startup), and only append a new record when a note appears or disappears — never rewrite unchanged state every tick.
- Also call `self.report(...)` for each transition (verbose console logging), consistent with the existing crawl/up logging style.

**C3. Graph display (minimal viable)**
- Expose active-note windows through the existing series/catalog API response.
- In `chart.ts`, add a lightweight annotated marker (reusing the existing `markArea`/`markLine` patterns already in `chartOption()`) spanning each note's active date range, so historical promo windows are visible on the timeline. Keep this visually subtle (e.g. a thin top-of-chart marker with a tooltip) rather than a new full styling system — can be extended later.

## Cluster D — Cross-provider account grouping (persistent alias)

Per user's decision: soft, reversible grouping — not the existing destructive `provider merge` (`src/ai_usage/provider_accounts.py:120-170`, `cli.py:1022-1065`), which stays as-is for its current one-time use case.

**D1. Config model**
- Add `group_id: str | None = None` to `AccountConfig` (`src/ai_usage/models.py:118-133`) and thread it through load/save in `src/ai_usage/config.py:66-99` / `118-129`.
- New CLI commands `ai-usage provider group <account-a> <account-b> [...]` / `provider ungroup <account>` to set/clear a shared `group_id` (generate a fresh id when grouping accounts that don't already share one; reuse the existing id if one side is already grouped).

**D2. Merged series building**
- In `src/ai_usage/graph.py`, the current grouping key is `(service, provider, account_id, metric_key)` (`graph.py:79-91`). When two or more accounts share a `group_id`, fold their series together per `metric_key`: merge point series by timestamp bucket, and where both sources have overlapping windows, keep the **max percentage** per the user's conflict-resolution decision. Windows/current-window metadata merge the same way (prefer the window with the higher `maximum_percentage` for any overlapping timeframe).
- Grouped output is presented as one logical series/account for graphing purposes; ungrouped accounts behave exactly as today (no change for the common case).

**D3. Frontend**
- `accountLabels`/catalog need to expose the resolved group label (first account's label, or a future configurable group label) so `ServicePanels.vue` and the chart legend show one entry per group instead of one per underlying account config.

## Verification
- Backend: `pytest` — extend `tests/test_progress.py`-style crawler tests for the notes diff-and-report logic (Cluster C2), add unit tests for `Metric.model` round-tripping through `history.py`/`orm.py` (Cluster B2), add tests for the `matching_providers` exclusion filter (Cluster A1), and add `graph.py` tests for group merging with overlapping/non-overlapping windows (Cluster D2). Run `ruff check` on all touched files.
- Frontend: `yarn vue-tsc --noEmit`, `yarn vitest run`, `yarn build` after each cluster (chart.ts marker additions, ServicePanels.vue styling, catalog/group label wiring).
- Manual: run `ai-usage serve` against real `~/.ai-usage` data (read-only, safe alongside a running `ai-usage up`) to confirm info-panel styling and the new note markers render without console errors; browser-automation pixel verification remains unavailable in this environment per the known tooling limitation, so this stays a code-level + unit-test verification, disclosed as such.

## Todos

- [x] A1: fix provider-add duplicate advanced listing
- [x] A2: info panel styling polish
- [x] B1: statusline fallback to cli-usage when stale
- [x] B2: record model with each metric
- [x] C1: parse promo/notice banners
- [x] C2: notes storage with change-only writes + verbose report
- [x] C3: graph display of active-note windows
- [x] D1: account group_id config + CLI group/ungroup
- [ ] D2: merged series building for grouped accounts *(in progress)*
- [ ] D3: frontend group label wiring
- [ ] Verification pass
