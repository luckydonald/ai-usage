Confirmed: no dedicated "model" field anywhere in the codebase — `Metric` has an untyped `metadata: dict[str, Any]` catch-all instead, which is the only existing place a model name could be stashed today.

## 1. Claude statusline provider and staleness

- **`src/ai_usage/providers/claude.py:344-411`** — `ClaudeStatusProvider` (key `"statusline"`). It reads a relay JSON file (written by a hook script installed via `install_status_relay`, `claude.py:471-523`) that Claude Code's `statusLine` command writes on every prompt.
- Staleness check already exists at **`claude.py:373-391`**: computes `age = time.time() - relay_file.stat().st_mtime`, compares to a configurable `stale_seconds` option (`claude.py:352`, default 120s), and sets `status=FetchStatus.STALE` (defined in `src/ai_usage/models.py:14`) with an explanatory `error` message when stale — **but it still returns the stale relay data**, it does not currently re-invoke `run_claude_usage`/`/usage` (that only happens today when the relay file is missing/empty, falling through to lines 395-402, which is `ClaudeUsageProvider`'s `cli-usage` logic, key `"cli-usage"` at `claude.py:414-428`). So "fall back to cli-usage if stale" would mean changing the `age <= stale_seconds` branch at line 384 to fall through to `run_claude_usage(...)` instead of returning `FetchStatus.STALE`.
- Similar precedent: `src/ai_usage/providers/codex.py:36,391-438` detects staleness via a `"limits may be stale"` warning string in CLI output rather than file mtime.
- Unrelated: `src/ai_usage/completion_staleness.py` is shell-completion staleness, not usage data.

## 2. Model field in usage data model

- **`src/ai_usage/models.py:41-58`** `Metric` — fields: `key, name, usage, observed_at, reset_at, window_seconds, metadata: dict[str, Any]`. No `model` field.
- Storage mirrors this: **`src/ai_usage/orm.py:45-66`** `MetricSampleRecord` (SQLite index) and jsonl history files at `HistoryStore.event_path` (`src/ai_usage/history.py:38-49`), persisted via `HistoryEvent.model_dump_json()` (`history.py:71`) and reloaded via `metadata_json` (`history.py:176`, `orm.py:66`).
- Today, "model" only appears indirectly: `claude_metric_key()` (`claude.py:45-54`) folds a model name into the metric `key`/`name` for per-model weekly windows (e.g. `seven-days-claude-opus-4-...`), and `parse_usage_output` stashes `reset_text` in `metadata` (`claude.py:94`).
- Adding a proper field is straightforward: add `model: str | None = None` to `Metric`, a matching nullable column to `MetricSampleRecord`, and a mapping line in `history.py`'s dict-building (~line 176) and the SQLite upsert; existing jsonl files remain valid since pydantic fields are additive/optional.
- Raw CLI output confirms model names are readily available: `ai/references/console-output/claude/motd/normal-team.txt:7` shows `Sonnet 5 with medium effort · Claude Team`; `ai/references/console-output/codex/motd/normal.md:4,15` shows `model: gpt-5.6-sol medium`.