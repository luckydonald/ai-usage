Have enough to report now.

## Findings

**1. `orm.py` (93 lines) — no per-fetch "raw result" table.** Three relevant tables: `MetricSampleRecord` (line 47-67, one row per metric per fetch, with an unused-looking `metadata_json` free-form column at line 66), `FetchRunRecord` (line 70-80, just id/account/timestamps/success/error — no payload), `CrawlStateRecord` (line 83-92). There is **no** JSON blob column anywhere that persists a whole `ProviderFetchResult`. Nothing beyond `Metric` objects is captured structurally in SQL.

**2. `collector.py` fetch_account (line 34-115) — anything on `ProviderFetchResult` besides `.metrics`/`.status`/`.error` is silently dropped.** It calls `provider.fetch()` (line 67), then `history.append_result(result)` (line 68) which — per `history.py` — only iterates `result.metrics` (line 58 of history.py). The rest of collector.py only reads `result.metrics` (loop line 69-78) and `result.status`/`result.error` (lines 103-111) for reporter strings. **If you added `account_info: dict | None` to `ProviderFetchResult`, collector.py would compile fine and just never look at it — completely dropped, no error.** You'd need to explicitly add code in collector.py (or history.py) to persist it.

**3. `history.py` — schema is metric-only, JSONL append-only + SQLite index (`MetricSampleRecord`).** `append_result` (line 55-79) builds one `HistoryEvent` per `Metric` (models.py line 88-96: `schema_version, event_id, source_id, service, provider, account_id, metric`) — there's no slot in `HistoryEvent` for account-level (non-metric) data at all. No existing "account label fetched live" concept anywhere in history.py.

Regarding a free-form label field: `AccountConfig` (models.py line 72-85) has `options: dict[str, Any]` (line 81) — this is the natural "underused field" already used for provider-specific config (e.g. discovery options in `config.py` line 122 `discovered_options`). It's user/discovery-populated, not currently used for anything fetched live from the API.

**4. Frontend — nothing exists for this today.** `types.ts` `Account` (line 1-8) is just `{id, service, provider, name, enabled, colors}`. `CatalogMetric`/`LatestMetric`/`GraphSeries` are all metric-shaped. No plan/subscription/email/display-name concept anywhere in the type file. This would be **net-new frontend work**: new type, new API field, new UI surface (likely near the account header/list).

**5. No precedent for a provider rewriting `AccountConfig` fields from a live fetch.** The only place `AccountConfig` gets rewritten post-creation, other than user-initiated `cli.py rename` (line 892) and `merge`/`remove` (line 842), is `host_identity.py` `add_host_to_account`/`remove_host_from_account` (lines 79-95) — but that only ever touches the `hosts` list, driven by local host-identity resolution, not by data returned from a provider's `fetch()`/`discover()`. `discover()` (claude.py:98, codex.py:154) returns `DiscoveredAccount` objects used only at account-creation time (`cli.py` line 178-182, `account_name = ... discovered.account.name ...`) — never re-invoked to refresh an existing account's identity fields after creation.

### Bottom line for scoping
There is no existing seam that stores anything beyond `Metric` samples per fetch. To add account identity/subscription data you'd need at minimum:
- A new field on `ProviderFetchResult` (models.py:61-69) — currently a no-op if added alone.
- Explicit new persistence: either (a) extend `FetchRunRecord` (orm.py:70-80) with nullable JSON/text columns for the raw identity/subscription payload (cheapest — it already exists per-fetch and is otherwise a thin row), or (b) a new small ORM table keyed by `account_id` holding "latest known" identity/subscription (more correct semantically since this is account-level, not fetch-level, data — avoids duplicating on every fetch).
- New code in `collector.py` to actually read and persist the new field (nothing does this automatically).
- New frontend type + API surface + UI (entirely new, nothing to reuse in `types.ts`).
- `AccountConfig.options` (models.py:81) is the closest "already-there, underused free-form dict" if you want a cheap read path for last-known values without a new table, but nothing currently writes into it from a live fetch — you'd be establishing new precedent, not reusing an existing pattern.