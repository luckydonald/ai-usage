Now I have a complete picture. Let me report findings.

## Findings

**1. No `--log-level` / `-v`/`--verbose` CLI option exists.**

I searched `src/ai_usage/cli.py` (1608 lines, uses Typer/Click) for any verbosity flag and found none. All `typer.Option(...)` definitions in the file are things like `--account`, `--no-input`, `--host`, `--port`, `--detach/-d`, `--serve/--no-serve`, `--older-than-days`, `--name`, `--secret-json`, `--hostname`, `--host-id`, etc. — no `--log-level`, `--verbose`, or `-v` anywhere in the file, and no `logging` import in `cli.py` at all.

**2. No `logging.basicConfig`/`dictConfig` call anywhere in the package.**

`grep -rn "basicConfig\|dictConfig" src/ai_usage/` returns nothing. There is no logging setup/init module. This means:
- No handlers are attached beyond Python's logging "handler of last resort" (which emits to stderr at WARNING and above only when no handlers are configured).
- Effective default level is `WARNING` (Python's root logger default) since nothing calls `setLevel`/`basicConfig`.
- So today, any `LOGGER.info(...)` call in this codebase is effectively silent by default (nothing configures INFO to be visible).

**3. Logger names/hierarchy**

Loggers are created ad hoc per-module, no central `ai_usage` root logger is explicitly instantiated in `__init__.py` (checked — no `getLogger`/`LOGGER` there):

- `src/ai_usage/completion_staleness.py:23` — `logging.getLogger(__name__)` → `"ai_usage.completion_staleness"`
- `src/ai_usage/config.py:14` — `logging.getLogger(__name__)` → `"ai_usage.config"`
- `src/ai_usage/webview_login.py:14` — `logging.getLogger(__name__)` → `"ai_usage.webview_login"`
- `src/ai_usage/providers/codex.py:29` — `logging.getLogger(__name__)` → `"ai_usage.providers.codex"`
- `src/ai_usage/providers/claude.py:36` — `logging.getLogger(__name__)` → `"ai_usage.providers.claude"`
- `src/ai_usage/git_backup.py:12` — `logging.getLogger("ai_usage.git_backup")` (explicit string, same result)
- `src/ai_usage/api.py:41` — `logging.getLogger("ai_usage.api")` (explicit string)

So the hierarchy is implicitly `ai_usage.*` via `__name__`-based loggers, but since no root config exists, there's no shared handler/formatter/level applied across it — each just falls back to Python defaults.

**4. Crawling/fetching/collecting status messages: these do NOT go through `LOGGER.info` — they go through a separate `ProgressReporter` callback, not `logging`.**

`src/ai_usage/progress.py` defines:
```python
ProgressReporter = Callable[[str], None]

def quiet_reporter(message: str) -> None:
    del message
```
`Collector` (`collector.py`) and `Crawler` (`crawler.py`) both default `reporter` to `quiet_reporter` (i.e., silent by default), and `self.report = reporter`. All the actual "status" strings use `self.report(...)`, e.g.:

- `collector.py:70-73` — `self.report(f"Started {operation} {account.name} ({account.service}/{account.provider}, {account.id}).")`
- `collector.py:101-104` — `self.report(f"{account.name}'s {metric.name} got a new value to store ({percentage(old_value)} -> {percentage(new_value)}).")`
- `collector.py:132` — `self.report(f"{account.name}: {result.error} — reusing last known values.")`
- `collector.py:134-137` — `self.report(f"Done {operation} {account.name} in {elapsed:.1f}s ({len(result.metrics)} metrics).")`
- `collector.py:139` — `self.report(f"Failed {operation} {account.name} in {elapsed:.1f}s: {error}")`
- `crawler.py:58` — `self.report(f"Config reload: account added - {label}.")`
- `crawler.py:61` — `self.report(f"Config reload: account removed or disabled - {removed_id}.")`
- `crawler.py:70` — `self.report(f"Config reload: git backup {'enabled' if enabled else 'disabled'}.")`
- `crawler.py:88` — `self.report(f"{account.name}: note {verb} - {transition.text}")`
- `crawler.py:118` — `self.report(f"Crawling {len(accounts)} account(s) {reason}: {names}.")`
- `crawler.py:166-169` — `self.report(f"{account.name}: backing off crawl interval to {backoff} seconds after failure {state.failure_count}.")`
- `crawler.py:174-177` — `self.report(f"{account.name}: limits reported as stale, rechecking in {STALE_RECHECK_SECONDS} seconds.")`
- `crawler.py:198-201` — `self.report(f"{account.name}: decreasing crawl interval to {intervals['active_seconds']} seconds after usage increased.")`
- `crawler.py:203-206` — `self.report(f"{account.name}: restoring crawl interval to {intervals['normal_seconds']} seconds.")`
- `crawler.py:209` — `self.report(f"{account.name}: next crawl in approximately {interval} seconds.")`
- `crawler.py:219` — `self.report(f"Crawler started for {len(accounts)} accounts: {names}.")`
- `crawler.py:221` — `self.report("Crawler started with no enabled accounts; waiting for configuration.")`

At the CLI call sites, `reporter=click.echo` is passed in explicitly:
- `cli.py:97` — inside `ApplicationState.__init__` (used by `up`/server flows)
- `cli.py:1307` — in the `crawl` command, `Crawler(..., reporter=click.echo, ...)`
- `cli.py:1495` — in `run_server_and_crawler(...)`, `reporter=click.echo`

So for the CLI commands (`crawl`, `up`), status messages print directly to stdout via `click.echo`, bypassing `logging` entirely.

The one place where `LOGGER.info` is used as the reporter default (not `click.echo`) is **`src/ai_usage/api.py`**, when the API/server code is used as a library rather than through the CLI's own wiring:
- `api.py:45` — `def __init__(self, paths: Paths, reporter: ProgressReporter = LOGGER.info)` (logger name `"ai_usage.api"`)
- `api.py:79` — `def create_app(paths: Paths, reporter: ProgressReporter = LOGGER.info) -> FastAPI`
- `api.py:347` — same default in another server-boot function
- `api.py:352` — `LOGGER.warning(...)` (an actual explicit warning-level call, unrelated to crawl status)

Other `LOGGER.info` calls in the whole codebase are only in `git_backup.py:90` (`"git backup: committed changes in %s."`) and `git_backup.py:97` (`"git backup: pushed successfully."`) — these do use INFO level, but again, with no `basicConfig`, they won't be visible on the console by default.

### Summary of gaps relative to what you're asking
- There is no `--log-level`/`-v` flag to add — you'd be introducing it fresh in `cli.py`'s `main_callback` (around `cli.py:235-246`) or as an app-level Typer callback option.
- There is no central logging setup — you'd need to add a `logging.basicConfig(...)`/`dictConfig(...)` call, probably in `main_callback` or a new `logging_setup.py`, since currently nothing configures handlers/levels/format for the `ai_usage` hierarchy.
- Crawl/fetch "status" messages (the ones you likely care about for `-v`) are architecturally decoupled from `logging` — they flow through the `ProgressReporter` callback (`quiet_reporter` by default, `click.echo` when wired from the CLI). If you want a `-v`/`--log-level` flag to control these, you'd either need to bridge `ProgressReporter` calls into `LOGGER.info(...)` (as `api.py` already does for its own default) and then rely on the new logging config's level, or filter based on the CLI flag before calling `click.echo`.