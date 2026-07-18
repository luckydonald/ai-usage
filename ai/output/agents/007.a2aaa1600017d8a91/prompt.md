Repo /home/user/git/luckydonald/ai-usage. Read-only research.

I need to add "account identity" (display name, email) and "subscription status" (plan type, renewal/expiry date, billing status) data to providers (claude.py, codex.py web-API providers), captured from live API responses. This is in addition to existing per-fetch `Metric` usage data.

Question: what's the least invasive place to store/surface this, given existing architecture? Investigate:

1. `src/ai_usage/orm.py` — full schema. Is there a `HistoryRecord`/similar per-fetch table that stores metrics? Does `ProviderFetchResult` (models.py) get persisted as-is (e.g. via a JSON column) or does the collector extract just `metrics` into per-metric rows, discarding anything else on the result object?
2. `src/ai_usage/collector.py` — `Collector.fetch_account()`/`fetch_all()` — what parts of `ProviderFetchResult` actually get written to the DB/history store vs just used for reporter messages? If I added a new optional field to `ProviderFetchResult` (e.g. `account_info: dict | None`), would collector.py currently even look at it / persist it, or would it just be silently dropped?
3. `src/ai_usage/history.py` (`HistoryStore`) — what's actually written per fetch (schema of `HistoryRecord` or similar) — percentage snapshots per metric? Any place a free-form "account label" string could naturally live already (e.g. does `AccountConfig` have an underused field, or does the frontend/API already surface anything like "account display name" fetched from the provider rather than user-typed)?
4. Frontend: does `frontend/src/types.ts` or the dashboard already have a slot for "account subscription status" / "plan type" anywhere, or would surfacing this be entirely new frontend work too?
5. Is there precedent for a provider enriching `AccountConfig.name` or similar from a live fetch (vs. only at `discover()` time)? Check if `AccountConfig` fields are ever rewritten after initial creation by anything other than user-initiated `provider rename`.

Report tight, cite file:line, under 300 lines. This is to inform a design/scope decision, not to write code.