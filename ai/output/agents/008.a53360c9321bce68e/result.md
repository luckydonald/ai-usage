## Research Report

### 1. `Paths` definition — `src/ai_usage/settings.py:10-55` (not `paths.py`; that file doesn't exist)

```python
@dataclass(frozen=True, slots=True)
class Paths:
    root: Path              # ~/.ai-usage (or $AI_USAGE_HOME)
    services: Path          # root/services   -- account YAML configs
    history: Path           # root/history    -- append-only jsonl metric history
    local: Path             # root/local      -- PRIVATE/excluded
    database: Path          # root/local/state.sqlite3
    credential_key: Path    # root/local/credential.key
    logs: Path              # root/local/logs
    frontend: Path
```

`ensure()` (settings.py:41-54) creates `.gitignore` at `root/.gitignore` containing `"/local/\n"` if missing — this is the exact, already-established shared-vs-private split.

**git_backup.py:15** — `TRACKED_PATHS = (".gitignore", "history", "services")`. `maybe_run_git_backup` (git_backup.py:43-96) runs `git add .gitignore history services` then commits/pushes at `paths.root`. **`local/` is never staged** — both because it's outside `TRACKED_PATHS` and because `.gitignore` excludes it. So:

- **Shared/git-backed**: `paths.services`, `paths.history`, `.gitignore` itself.
- **Private/local**: `paths.local` (→ `state.sqlite3`, `credential.key`, `logs/`, plus `git_backup_state.json` and `host_id.json` written directly there).

`host_identity.py:22-23` confirms: `local_host_identity_path(paths) = paths.local / "host_id.json"` — matches your recollection exactly (field is `paths.local`, not `paths.root/"local"` computed inline — it's the dataclass field).
`git_backup.py:24` similarly: `_state_path(paths) = paths.local / "git_backup_state.json"`.

### 2. `ConfigStore` — `src/ai_usage/config.py`

Accounts are stored **one YAML file per account**, not one big file: `services/<service>/<account_id>.yml` (config.py:60-70, `save_account`). Written via a temp-file + atomic `.replace()` pattern (`path.with_suffix(".yml.tmp")`, config.py:64-69). Loaded via `list_accounts()` (config.py:37-50), which globs `paths.services.glob("*/*.yml")` and does `AccountConfig.model_validate(loaded)`. `global_config()` (config.py:25-35) reads a separate single file, `root/config.yml` (note: **not** under `services/`, and not in `TRACKED_PATHS` either — currently `config.yml` is untracked by git_backup!).

`AccountConfig` exact fields — `src/ai_usage/models.py:72-85`:
```python
class AccountConfig(BaseModel):
    id: str
    service: str
    provider: str
    name: str
    enabled: bool = True
    removed_at: datetime | None = None
    credential_id: str | None = None
    discovery_fingerprint: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    colors: dict[str, str] = Field(default_factory=dict)
    intervals: dict[str, int] = Field(default_factory=dict)
    hosts: list[tuple[str, str]] | None = None
```
To add new structured identity/subscription fields, the natural spot is a new typed field (or nested model) on `AccountConfig`, persisted automatically through `save_account`'s `account.model_dump(mode="json")` → yaml dump (config.py:66) — no separate serialization code needed, it's whole-model dump/load.

### 3. Precedent for "shared config file" vs "private/sensitive file"

Confirmed via `database.py` and `orm.py`: credentials are **not** stored as a private YAML sibling — they live **encrypted inside the SQLite DB** (`CredentialRecord`, orm.py:14-25: `ciphertext`, `nonce`, `encryption_version`), and that DB file (`paths.database = root/local/state.sqlite3`) sits inside `paths.local`, which is excluded from git as shown above. The encryption key itself (`paths.credential_key = root/local/credential.key`, database.py:34 `CredentialCipher.load(paths.credential_key)`) is also under `local/`.

So the existing precedent is: **sensitive data → `local/` (private, non-git, and here also encrypted in SQLite)**; **non-sensitive structured data → files directly under `root/` that are in `TRACKED_PATHS` (`services/`, `history/`)**. There is no existing precedent for a private *sibling YAML/JSON file per account* — the precedent instead is "put it in `paths.local`", e.g. as a per-account JSON blob such as `paths.local / "raw" / f"{account.id}.json"`, mirroring how `host_id.json` and `git_backup_state.json` sit directly in `local/`. This is what to reuse for raw provider payloads rather than inventing a new directory root.

One nuance: `root/config.yml` (global config) is currently **not staged by git_backup** (`TRACKED_PATHS` only has `.gitignore, history, services` — config.yml is silently excluded, likely an existing gap/bug, not something to imitate for "shared" data — put new shared account fields on `AccountConfig`/`services/*.yml`, which *is* tracked, not in `config.yml`).

### 4. `orm.py` — DB-as-cache-over-YAML pattern

There is **no existing table that mirrors `AccountConfig` into SQL** — `AccountConfig` is YAML-only; SQL (`orm.py`) is used exclusively for: `CredentialRecord` (encrypted secrets), `SourceRecord`/`IndexedFileRecord` (history-file indexing/dedup), `MetricSampleRecord` (flattened metric cache for fast queries, mirrors `history.py`'s jsonl — this **is** the DB-as-cache-over-file-source-of-truth pattern you're looking for), `FetchRunRecord` (run bookkeeping), and `CrawlStateRecord` (scheduler cache: `account_id` PK, `next_run_at`, `active_until`, `failure_count`, `last_percentage`, `last_error` — orm.py:83-92).

`CrawlStateRecord` is the closest structural template: a small table keyed by `account_id` (String(36) PK) caching a handful of scalar fields for fast reads, populated/refreshed by the collector on each fetch. A new table (e.g. `AccountIdentityRecord`) with `account_id` PK plus `name`, `email`, `plan_type`, `renewal_at`/`reset_at`, `billing_status`, `updated_at` would match this exact pattern — cache written on each successful fetch (alongside where `CrawlStateRecord` gets upserted, likely in `collector.py` near `history.append_result`/`FetchRunRecord` update, collector.py:60-80), with `services/<service>/<id>.yml` (`AccountConfig`) remaining the durable/git-backed source of truth per the decision already made.

**Key files/lines for implementation:**
- `src/ai_usage/settings.py:10-55` (`Paths`)
- `src/ai_usage/config.py:60-70` (`save_account`), `:37-50` (`list_accounts`)
- `src/ai_usage/models.py:72-85` (`AccountConfig`)
- `src/ai_usage/git_backup.py:15` (`TRACKED_PATHS`)
- `src/ai_usage/orm.py:83-92` (`CrawlStateRecord`, template to copy)
- `src/ai_usage/database.py:74-111` (credential put/get pattern, for reference on session usage)
- `src/ai_usage/collector.py:33-80` (`fetch_account`, where to hook new cache writes)