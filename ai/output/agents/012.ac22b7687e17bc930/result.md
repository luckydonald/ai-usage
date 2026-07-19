I now have a complete picture. Here is the report.

## 1. CLI entry points for `crawl` and `up`

- `/home/user/git/luckydonald/ai-usage/src/ai_usage/cli.py`
  - `crawl` command: lines 1229-1260. Builds a `Runtime`, then a `Crawler(runtime.collector, runtime.config, runtime.database, reporter=click.echo, host_id=identity.host_id)` and calls `await crawler.run()`.
  - `up` command (function `run_all`): lines 1403-1445. Initializes a `Runtime` just to run `ensure_ready_to_crawl`, closes it, then calls `ai_usage.api.run_server_and_crawler(paths, host, port, reporter=click.echo, explicit_port=explicit_port, host_id=identity.host_id)`.
  - Both commands support `--detach` (spawns a detached background process, see `detach()` helper) and both funnel into the same `Crawler` class.
- `/home/user/git/luckydonald/ai-usage/src/ai_usage/api.py`
  - `run_server_and_crawler()` (lines 279-308): builds a FastAPI app via `create_app()`, gets `runtime: ApplicationState = app.state.runtime`, runs `runtime.crawler.run()` and `server.serve()` concurrently in an `asyncio.TaskGroup`.
  - `ApplicationState` class (lines 36-68) constructs its own `Database`, `ConfigStore`, `Collector`, and `Crawler` instances (independent of the CLI's `Runtime` class in cli.py, but structurally identical).

Both `crawl` and `up` ultimately run the same `Crawler.run()` loop from `crawler.py`.

## 2. How accounts/providers are loaded — already re-read every tick, no caching

`ConfigStore` (`/home/user/git/luckydonald/ai-usage/src/ai_usage/config.py`) has **no in-memory cache at all**. Every call hits disk:

```python
def list_accounts(self, enabled_only: bool = True) -> list[AccountConfig]:
    accounts: list[AccountConfig] = []
    if not self.paths.services.exists():
        return accounts
    for path in sorted(self.paths.services.glob("*/*.yml")):
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        account = AccountConfig.model_validate(loaded)
        if not enabled_only or account.enabled:
            accounts.append(account)
    return accounts
```

In `crawler.py`, `Crawler.tick()` (lines 66-87) calls `self.config.list_accounts()` fresh at the top of **every** tick:

```python
async def tick(self) -> None:
    accounts = self.accounts_for_this_host(self.config.list_accounts())
    await self.ensure_states(accounts)
    ...
```

`Crawler.run()` (lines 159-178) schedules `tick` to run every 1 second via `FastScheduler`, so the account list is effectively already reloaded from disk once per second. New account YAML files appear in `list_accounts()` on the very next tick; `ensure_states()` immediately creates a `CrawlStateRecord` with `next_run_at=now`, so a newly added account gets fetched on that same tick.

Removed accounts: `provider remove` (cli.py lines 907-975) doesn't delete the file by default — it rewrites the account with `enabled=False` and `removed_at=<now>` via `runtime.config.save_account(removed)` (only deletes the YAML file if `--delete-history` is passed, via `runtime.config.delete_account(removed)`). Since `list_accounts()` defaults to `enabled_only=True`, a disabled/removed account simply stops appearing in the very next tick's list — no extra reload step is needed.

**Conclusion: account add/remove is already "live" today, at ~1-second granularity, because there is no caching layer to invalidate.**

## 3. Config storage mechanism

Two storage locations, both under `Paths` (`/home/user/git/luckydonald/ai-usage/src/ai_usage/settings.py`), rooted at `$AI_USAGE_HOME` or `~/.ai-usage`:

- **YAML files on disk** (via `ConfigStore` in `config.py`):
  - `paths.root / "config.yml"` — global settings (e.g. git-backup/"autocommit" flag, intervals). Read via `global_config()` / `structured_global_config()` (returns `GlobalConfig` pydantic model, `models.py` line 95), written via `save_global_config()` (merge + atomic temp-file replace).
  - `paths.services / <service> / <account_id>.yml` — one file per account, `AccountConfig` model (`models.py` line 118). Read via `list_accounts()`/`get_account()`, written via `save_account()`, deleted via `delete_account()`.
- **SQLite database** (`paths.database` = `paths.local / "state.sqlite3"`, via `Database` in `database.py`, SQLAlchemy async + Alembic migrations in `/home/user/git/luckydonald/ai-usage/alembic/versions/0001_initial.py`, ORM models in `orm.py`):
  - `CredentialRecord` — encrypted credentials (`CredentialCipher`/`crypto.py`, key at `paths.credential_key` = `paths.local / "credential.key"`).
  - `SourceRecord`, `IndexedFileRecord`, `MetricSampleRecord`, `FetchRunRecord`, `CrawlStateRecord` (per-account next-run scheduling state, failure counts, backoff, active-window tracking — this is what `Crawler.update_state()` reads/writes each tick).

There is no config caching layer anywhere — every read (`global_config()`, `list_accounts()`, `get_account()`) re-parses the YAML files from disk on each call.

## 4. Main loop structure of crawl/up

`Crawler` class, `/home/user/git/luckydonald/ai-usage/src/ai_usage/crawler.py`:

- `run()` (lines 159-178): logs startup message, then creates `self.scheduler = FastScheduler(state_file=str(paths.local/"fastscheduler.json"), quiet=True)`, registers `self.scheduler.every(1).seconds.no_catch_up().do(self.tick)`, calls `self.scheduler.start()`, then just does `while True: await asyncio.sleep(1)` until cancelled, finally `self.scheduler.stop()` in a thread.
- `tick()` (lines 66-87): the actual per-iteration work — re-reads accounts (§2 above), filters to accounts due (`CrawlStateRecord.next_run_at <= now`, checked in SQLite), calls `self.collector.fetch_all(due, operation="crawling")`, updates each account's `CrawlStateRecord` via `update_state()`, then calls `maybe_run_git_backup(self.database.paths, self.config, now)` (git_backup.py) at the end of every tick.
- `update_state()` (lines 89-157): adaptive interval logic (active/normal/backoff seconds with jitter), reads `self.config.intervals_for(account)` which itself reads `global_config()` fresh each call.

**Insertion point for any explicit "reload config" step**: the natural place is at the top of `tick()` (called every ~1s already) or inside `run()`'s scheduler registration. Since config reads are already fresh per call, a "reload" hook would really only be needed if a caching layer is later introduced, or if you want an explicit reconciliation step (e.g., detecting removed `CrawlStateRecord`s for accounts that vanished, or force-triggering `maybe_run_git_backup`/`ensure_states` off-cycle).

## 5. Existing file-watching / signal-handling / reload mechanism

None found for config reload. Grep across `src/ai_usage/` for `signal`, `SIGHUP`, `SIGTERM`, `watchdog`, `inotify`, `watchfiles`, `reload_config`, `lru_cache`, `functools.cache` turned up only:
- `webview_login.py` lines 198/211 — `signal.signal(signal.SIGINT, handle_sigint)` used only for the interactive OAuth webview login flow (Ctrl-C handling), unrelated to crawl/up.
- `services.py` — `systemctl --user daemon-reload` calls, related to installing the systemd user service (`install_service`/`uninstall_service`), not to in-process config reload.

There is no SIGHUP handler, no file watcher, and no explicit "reload" command/mechanism anywhere in the codebase.

## 6. Where "autocommit" (git-backup) setting is read/used

The codebase does not use the word "autocommit" anywhere (confirmed via grep — zero hits for `autocommit`/`auto_commit`/`auto-commit`). The equivalent feature is called **git backup**, controlled by `GlobalConfig.git.enabled` (`GitBackupConfig` in `models.py` lines 88-92, default `False`).

- **CLI commands** to toggle it, `/home/user/git/luckydonald/ai-usage/src/ai_usage/cli.py`:
  - `config_git_enable()` (lines 1335-1342): `ConfigStore(paths).save_global_config({"git": {"enabled": True}})`
  - `config_git_disable()` (lines 1345-1352): same with `False`
  - `config_git_status()` (lines 1355-1362): reads `ConfigStore(paths).structured_global_config().git.enabled`
  - These are registered under `config_git_app` (`config git enable|disable|status`), a sub-typer of `config_app` (line 75-80).
- **Read/consume path**: `/home/user/git/luckydonald/ai-usage/src/ai_usage/git_backup.py`:
  - `git_backup_enabled(config: ConfigStore) -> bool` (line 18): `return config.structured_global_config().git.enabled` — re-reads `config.yml` from disk every call, no caching.
  - `maybe_run_git_backup(paths, config, now, debounce_seconds=600)` (lines 43-102): checks `git_backup_enabled(config)` first; if disabled, returns immediately without committing. Also debounces actual git commit/push to at most once per 600s using a state file `paths.local / "git_backup_state.json"` (via `_last_attempt`/`_record_attempt`).
  - This is called from **every** `Crawler.tick()` (crawler.py line 86: `await asyncio.to_thread(maybe_run_git_backup, self.database.paths, self.config, now)`), and also from the one-shot `fetch` CLI command (cli.py line 1214-1216).

**Conclusion: the autocommit/git-backup toggle is already re-read live every tick** (every ~1 second, same as account list), since `git_backup_enabled()` re-parses `config.yml` on each call with no caching — turning it on/off via `config git enable`/`disable` while `crawl`/`up` is running already takes effect on the next tick (the actual commit itself still respects its own independent 600s debounce window, separate from the enabled/disabled check).