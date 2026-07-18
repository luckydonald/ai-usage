# Typer CLI migration, fixed chart axis range, and legend-hide bugfix

## Context

Three unrelated fixes/changes requested together:

1. Switch the CLI framework from Click to Typer (full migration, not a thin wrapper).
2. The time-range preset (`auto`/`1h`/`3h`/.../`all`) only filters which data is *fetched* — it never constrains the chart's x-axis, so echarts auto-scales the axis to whatever data happens to exist in that window. A "3h" range with a 45-minute-old last sample renders a ~45-minute-wide chart instead of a 3-hour-wide one.
3. Recent work (this session's prior /plan) added a legend↔filter sync (`App.vue` `toggleSeries`) that went further than intended: hiding a legend entry that empties out an account/metric mutates `filters.accounts`/`filters.metrics` and triggers a server refetch, which removes that series' data entirely — so the legend entry itself vanishes (nothing left to click to re-show it). The user wants disabling a metric to *just hide it* (client-side only), not exclude it from the fetch.

## Part 1 — Click → Typer migration

**Scope** (from exploration of `src/ai_usage/cli.py`): `main` has 14 registered top-level names (12 commands + 2 aliases: `deinstall`, `start`), `provider` has 11 registered names (7 commands + 4 aliases: `new`, `ls`, `info`, `del`/`rm`, `name`/`mv`) plus one nested subgroup `provider hosts` (2 commands + 1 alias `rm`).

- **`pyproject.toml`**: add `typer` to `dependencies` (keep the existing `click>=8.2` pin — Typer depends on Click 8 anyway).
- **`cli.py`**: convert to `app = typer.Typer(context_settings={"max_content_width": 120})`, `provider_app = typer.Typer()`, `app.add_typer(provider_app, name="provider")`, `hosts_app = typer.Typer()`, `provider_app.add_typer(hosts_app, name="hosts")`. Configure `rich_markup_mode=None` on every `Typer()` instance so help output stays Click's plain formatter (minimizes changes to the 15 existing `CliRunner` test assertions that check exact help-text layout like `"  provider "`, `"Usage:"`).
- **Bare-invocation status+help** (`main`'s `invoke_without_command` behavior, `cli.py:209-218`): becomes `@app.callback(invoke_without_command=True)` taking `ctx: typer.Context`; same `ctx.invoked_subcommand`/`ctx.get_help()` calls work unchanged since Typer's Context is Click's.
- **Command aliasing** (10 `add_command` call sites — `provider_group.add_command(fn, "alias")` etc.): Typer's decorator API has no direct equivalent, but since `typer.main.get_command(app)` returns the real underlying `click.Group`, register aliases exactly as today by calling `.add_command(existing_click_command, "alias")` on that extracted Click group *after* building the Typer app — same pattern, one layer down. Concretely: build the Typer apps and their `@app.command()`/`@provider_app.command()` functions first, then do the alias wiring at module bottom via the extracted Click command objects (mirrors current `main.add_command(...)`/`provider_group.add_command(...)` lines almost verbatim).
- **Per-parameter conversions** — mechanical, one pattern per Click feature already in use:
  - `click.option`/`click.argument` → `Annotated[T, typer.Option(...)]` / `Annotated[T, typer.Argument(...)]`, one per existing option/argument (help text comes from the same docstrings Typer already reads by default, so docstrings don't need to change).
  - `port: int | None = None` "explicit vs default" sentinel (`up`/`serve`) → same `Optional[int] = None` under Typer, no behavior change.
  - `--account` `multiple=True` (`fetch`) → `Annotated[list[str], typer.Option()]`.
  - `-d`/`--detach` short-flag alias → `Annotated[bool, typer.Option("--detach", "-d")]`.
  - `provider add`'s `ignore_unknown_options`/`allow_extra_args` + `context.args` (dynamic `--key value` passthrough) → same `context_settings` dict on that one `@provider_app.command(context_settings=...)`, `ctx.args` unchanged.
  - `click.Path(exists=True, dir_okay=False, path_type=Path)` (`--secret-file`) → keep passing a `click.Path` instance via `typer.Option(..., click_type=click.Path(exists=True, dir_okay=False, path_type=Path))`, or the simpler Typer-native `exists=True, dir_okay=False` kwargs on `typer.Option(Path, ...)` — use whichever keeps `Path` behavior identical.
  - `click.confirm`/`click.UsageError`/`click.ClickException` (used inside plain helper functions, not decorated commands) — untouched, still imported from `click` directly, fully compatible.
  - Dual positional-argument-or-`--account`-option pattern (`requested_account_id()`, `cli.py:613`) — untouched, still works identically since it's plain Python logic, not Click/Typer-specific.
- **`shell_completion.py`**: `install_completion(paths, main, shell)` currently type-hints `main: click.BaseCommand` and is called with the raw Click group. After migration, call it with `typer.main.get_command(app)` at the call site (`cli.py`'s `completion` command) instead of the bare `app`/`main` Typer object — `shell_completion.py` itself needs no internal changes since it only ever consumed a `click.BaseCommand`.
- **Entry point**: `pyproject.toml`'s `ai-usage = "ai_usage.cli:main"` — keep a thin `def main(): app()` wrapper (or point the entry point at `app` directly if Typer's `Typer.__call__` is compatible with being invoked as a zero-arg entry point, whichever needs less churn).
- **Tests**: run `tests/test_cli.py` and `tests/test_provider_commands.py` (15 `CliRunner` call sites) after conversion; fix any help-text-format assertions that still differ despite `rich_markup_mode=None` (expect most to pass unchanged, a few may need re-wording since Typer's plain-mode formatting isn't byte-identical to raw Click in every corner).

## Part 2 — Chart x-axis should span the requested range, not the data extent

**Root cause** (confirmed): `App.vue`'s `load()` computes `[start, end] = rangeForPreset(preset.value)` (`time.ts`) but only ever uses it as fetch query parameters (`api.ts`) — it's never stored or passed to `UsageChart.vue`/`chart.ts`. `chart.ts`'s `xAxis: { type: "time", ... }` (chart.ts ~128) sets no `min`/`max`, so echarts defaults to auto-scaling the time axis to the actual min/max timestamp present in the series data.

**Fix** (fixed axis, per decision):
- `App.vue`: store `[start, end]` from `load()` in refs (e.g. `rangeStart`/`rangeEnd`), pass them as new props to `<UsageChart>`.
- `UsageChart.vue`: accept `rangeStart: Date`/`rangeEnd: Date` props, pass through to `chartOption(..., { ...otherOptions, start: rangeStart, end: rangeEnd })`.
- `chart.ts`: `ChartOptions` gains `start`/`end`; when present, set `xAxis.min = start.getTime()` / `xAxis.max = end.getTime()` (numeric epoch ms, echarts' preferred form for a time axis) instead of leaving them auto-computed. The existing "now" markLine keeps using `now` (which already always equals `rangeForPreset`'s `end` for every preset today) — no change needed there.
- Reuse existing `ChartOptions` bag (already added last session for `now`/`legendSelected`) rather than adding new positional params.

## Part 3 — Legend toggle should only hide, never filter/refetch

**Root cause** (confirmed): `App.vue`'s `toggleSeries()` correctly maintains `hiddenSeriesKeys` (client-side-only visual hide, already wired end-to-end through `UsageChart.vue`'s `legendSelected()` → `chart.ts`'s `legend.selected`) but *additionally* computes `accountFullyHidden`/`metricFullyHidden` and overwrites `filters.accounts`/`filters.metrics` with an explicit allow-list excluding the now-fully-hidden account/metric, then calls `load()` — which refetches a narrower `series` from the server, permanently dropping that series (and its legend entry, since `chartOption` only ever renders series present in the array it's given) until the sidebar filters are manually reset.

**Fix**: delete the `accountFullyHidden`/`metricFullyHidden` computation and the `filters.accounts =`/`filters.metrics =`/`void load()` lines from `toggleSeries()` entirely. `toggleSeries()` becomes exactly: update `hiddenSeriesKeys` (add/remove the key), nothing else. The sidebar's own Accounts/Metrics multi-selects remain the only thing that changes `filters` and triggers a refetch — legend clicks become pure, reversible, client-side visibility toggles, matching every other echarts legend in existence. `pruneHiddenSeriesKeys()` (called after each real `load()`) stays as-is, since it's still needed to drop stale keys when a sidebar filter change legitimately removes a series from the fetched set.

## Verification

- Backend: `uv run pytest -q` after the Typer migration (expect all current tests green after fixing any help-format assertions).
- CLI manual smoke: `uv run ai-usage --help`, `uv run ai-usage provider --help`, `uv run ai-usage provider hosts --help`, exercise a couple of aliases (`uv run ai-usage provider ls`, `uv run ai-usage provider mv ...`), confirm `uv run ai-usage completion --shell bash` still renders a script.
- Frontend: `cd frontend && yarn test && yarn type-check && yarn build`; extend `frontend/src/chart.test.ts` with a case asserting `xAxis.min`/`xAxis.max` equal the passed `start`/`end` when provided. Manually verify in a browser (`yarn dev` or `ai-usage serve` against seeded data, per this session's established pattern): pick "3h", confirm the chart's visible x-axis spans the full 3 hours even with sparse data; click a legend entry off and back on, confirm the series fades/reappears instantly with no network refetch and the legend entry never disappears.

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
- [x] Phase E1: frontend dropdown presets auto/1h/3h/6h/12h
- [x] Phase E2: incremental chart redraw (no full reanimate)
- [x] Phase E3: vertical red dashed "now" line
- [x] Phase E4: prediction line legend + window-reset fixes
- [x] Phase E5: two-way legend/filter sync
- [x] Fix legend-hide bug (Part 3)
- [x] Fix chart axis range (Part 2)
- [ ] Migrate CLI from Click to Typer (Part 1) *(in progress)*
