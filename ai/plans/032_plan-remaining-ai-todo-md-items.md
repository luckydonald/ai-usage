# Plan: remaining `ai/todo.md` items

## Context
Two unchecked items remain in `ai/todo.md` (the rest are done; the working tree already holds uncommitted work for them in `chart.ts`, `graph.py`, etc. — leave it alone and build on top).
1. `todo:63a4e32b…` — mark the end of a usage block clearly on the chart.
2. `todo:6bea597f…` — crawler logs should carry the crawler's name (`[ai_usage.crawl.<service>.<provider>]`) instead of the generic `[ai_usage.crawl]`.

## 1. Block-end marker (frontend)
User chose: a solid vertical line at `window.end`, spanning 0..`maximum_percentage`, in the series color.

- `frontend/src/chart.ts`, `chartOption()`: the per-series `markArea` (≈ line 525) only has a 1px border. Add a `markLine` to the same "actual" series (or a sibling silent series, as `now-line` does) with one entry per window:
  `[{ xAxis: window.end, yAxis: 0 }, { xAxis: window.end, yAxis: window.maximum_percentage }]`, `symbol: "none"`, `silent: true`, `lineStyle: { color: item.color, width: 2, type: "solid" }`, `label: { show: false }`.
- Keep `silent: true` so it doesn't intercept the markArea hover/click tooltip path (`params.componentType === "markArea"`, ≈ line 477).
- Skip the line for the current window if `window.end` is in the future and equals the projected end? No — keep it; it marks where the block will end.
- Tests in `frontend/src/chart.test.ts`: assert the option contains an end markLine per window with the right x/y and that it is silent.

## 2. Per-crawler logger names (backend)
Today a single `CRAWL_LOGGER = logging.getLogger("ai_usage.crawl")` (`src/ai_usage/cli.py:97`) is passed as `reporter=CRAWL_LOGGER.info` (cli.py:113, 1431, 1679) into `Collector` / `Crawler` / `api.py` (`LOGGER = "ai_usage.api"`). Reporters are plain `Callable[[str], None]` (`src/ai_usage/progress.py`), so the logger name is fixed by whoever builds the callable. Log format already includes `[%(name)s]` (cli.py:324).

Approach — keep the `ProgressReporter` signature, add a named-logger helper:
- `src/ai_usage/progress.py`: add `crawl_logger(account) -> logging.Logger` returning `logging.getLogger(f"ai_usage.crawl.{account.service}.{account.provider}")` (names are slugs already; sanitize `.`).
- `Collector.fetch_account()` (`collector.py` ≈ lines 75, 106, 137–144) and `Crawler.update_state()` (`crawler.py` ≈ 146–211): these have the `account`; replace `self.report(...)` for account-scoped messages with `crawl_logger(account).info(...)`. Keep `self.report` for global messages (config reload, "Crawler started…", crawl batch summary) so they stay on `ai_usage.crawl`.
- Preserve the injected `reporter` for tests/quiet mode: make `report` take an optional `account` and have the default wiring route to the named logger only when the reporter is the stock `CRAWL_LOGGER.info`. Simplest: add `reporter_for(account)` on `Collector`/`Crawler` that returns `self.report` when a custom reporter was injected, else the named logger's `.info`. This keeps `tests/test_progress.py` (injects its own reporter) working unchanged.
- Since children of `ai_usage.crawl` propagate, existing level/handler config keeps working.

Tests: add to `tests/test_progress.py` (or collector tests) a `caplog` case asserting the record name is `ai_usage.crawl.claude.<provider>` for an account fetch, and `ai_usage.crawl` for the global start message.

## Verification
- `cd frontend && corepack yarn@4.9.2 run test --run src/chart.test.ts src/components/UsageChart.test.ts && corepack yarn@4.9.2 run type-check`
- `uv run pytest tests/test_progress.py tests/test_graph.py` (plus the full suite; diff failures against baseline before blaming this change).
- Visual: screenshot the dev instance (port 4458) and confirm the solid end line per block, not hijacking hover.
- Run the crawler briefly and confirm log lines show `[ai_usage.crawl.<service>.<provider>]`.
- On completion tick both boxes in `ai/todo.md` and call `mcp__sync_todo__complete_todo(calendar_id=7, uid=…)` for each uid.
