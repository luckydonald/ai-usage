## Findings

### 1. `parse_codex_status` / `CodexStatusProvider` tests

`tests/test_providers.py:47-52` — the only existing codex-status test, calling `parse_codex_status` directly (not `CodexStatusProvider.fetch`):

```python
def test_codex_status_converts_remaining_to_used() -> None:
    output = "Weekly limit: [████░] 94% left (resets 12:36 on 24 Jul)"
    metrics = parse_codex_status(output, datetime.now(UTC))
    assert len(metrics) == 1
    assert metrics[0].usage.percentage == 6
# end def
```

Note: there is **no existing test that exercises `CodexStatusProvider.fetch` or the STALE-status branch** (`src/ai_usage/providers/codex.py:246`: `status = FetchStatus.STALE if STALE_WARNING_PATTERN.search(output) else FetchStatus.SUCCESS`). Since `fetch` calls `run_codex_status`, which shells out to `pexpect.spawn`, testing `fetch` directly would require monkeypatching `run_codex_status` (or `pexpect`). The lighter-weight, style-consistent approach is to add a plain `parse_codex_status`-only test plus a raw string containing the "limits may be stale" phrase, matching the same fixture style as above, e.g. an output string like:

```python
def test_codex_status_flags_stale_warning() -> None:
    output = "Weekly limit: [████░] 94% left (resets 12:36 on 24 Jul)\nNote: limits may be stale."
```

— then separately assert `STALE_WARNING_PATTERN.search(output)` is truthy, or write a small `fetch`-level test that monkeypatches `ai_usage.providers.codex.run_codex_status` to return that string and asserts `result.status == FetchStatus.STALE`. `STALE_WARNING_PATTERN` is defined at `src/ai_usage/providers/codex.py:21`: `re.compile(r"limits may be stale", re.IGNORECASE)`.

### 2. `Crawler.update_state()` tests

There is **no `tests/test_crawler.py`**. The relevant tests live in **`tests/test_progress.py`**.

A STALE-status test for `update_state` already exists at `tests/test_progress.py:126-161` (`test_stale_result_is_not_treated_as_a_crawl_failure`) — this predates/matches your edit and only asserts on reporter messages (`"backing off crawl interval" not in messages`), not on `next_run_at`/`failure_count` directly via DB. You'll likely want to extend it (or add a new test) to also assert the DB-level fields your new `elif result.status == FetchStatus.STALE` branch sets (`src/ai_usage/crawler.py:114-121`): `state.next_run_at == now + timedelta(seconds=STALE_RECHECK_SECONDS)`, `state.failure_count == 0`, `state.last_error is None`.

There is **no dedicated FetchStatus.ERROR backoff test that reads `next_run_at`/`failure_count` from the DB** either — the ERROR path (`crawler.py:102-113`) is untested directly in the repo; only the STALE and SUCCESS/active-interval paths are covered via message assertions in `test_progress.py`.

Fixture/setup pattern used (`tests/test_progress.py:18-46, 84-122`):
```python
class StaleProvider(Provider):
    service = "test-service"
    key = "stale"
    display_name = "Stale test provider"

    async def fetch(self, account, credential):
        now = datetime.now(UTC)
        return ProviderFetchResult(
            service=self.service, provider=self.key, account_id=account.id,
            fetched_at=now, status=FetchStatus.STALE,
            error="no new statusline data yet (last update 3600s ago)",
            metrics=[Metric(key="five-hours", name="5-hour window",
                             usage=Usage(percentage=42.0), observed_at=now)],
        )
```
```python
paths = temporary_paths(tmp_path)          # from tests/test_storage.py:15-26
paths.ensure()
database = Database(paths)
await database.migrate()
history = HistoryStore(paths, database)
config = ConfigStore(paths)
account = AccountConfig(id="stale-account", service="test-service", provider="stale", name="Stale account")
registry = ProviderRegistry(); registry.register(StaleProvider())
messages: list[str] = []
collector = Collector(config, database, history, registry, reporter=messages.append)

result = await collector.fetch_account(account, operation="crawling")
crawler = Crawler(collector, config, database, reporter=messages.append)
await crawler.ensure_states([account])
now = datetime.now(UTC)
await crawler.update_state(account, result, now)
```

To assert directly on DB fields after `update_state`, use `database.sessions()` + `session.get(CrawlStateRecord, account.id)` (same pattern `Crawler` itself uses, `src/ai_usage/crawler.py:96-97`).

### 3. `CrawlStateRecord` fields (`src/ai_usage/orm.py:83-92`)

```python
class CrawlStateRecord(Base):
    __tablename__ = "crawl_state"
    account_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    active_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    last_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
```

DB setup helper: `temporary_paths(tmp_path)` in `tests/test_storage.py:15-26`, used with `Database(paths)` + `await database.migrate()`. `Crawler.ensure_states([account])` (`crawler.py:53-64`) creates the initial `CrawlStateRecord` row before calling `update_state`.