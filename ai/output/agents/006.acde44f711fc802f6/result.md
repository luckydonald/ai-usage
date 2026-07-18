Findings (all paths relative to `/home/user/git/luckydonald/ai-usage`):

**1. warnings vs logging vs reporter callback**

- `import warnings` / `warnings.warn(...)`: **not used anywhere** in `src/ai_usage/` (grep returned nothing).
- `logging` module: used in two places, each with its own module-level logger, standard pattern:
  - `src/ai_usage/api.py:5` `import logging`, `src/ai_usage/api.py:33` `LOGGER = logging.getLogger("ai_usage.api")`, then `LOGGER.warning(...)` at `src/ai_usage/api.py:288`.
  - `src/ai_usage/git_backup.py:4` `import logging`, `src/ai_usage/git_backup.py:12` `LOGGER = logging.getLogger("ai_usage.git_backup")`.
- `providers/claude.py` and `providers/codex.py` currently import neither `logging` nor `warnings` (only `asyncio, json, os, re, shlex, sys, time`, etc. — `src/ai_usage/providers/claude.py:3-12`). So today they have zero non-fatal-warning mechanism at all.
- There is a distinct **reporter callback pattern**, but it's a `ProgressReporter` (progress/status messages), not an error/warning channel: defined via `ai_usage.progress.ProgressReporter` / `quiet_reporter` (`src/ai_usage/progress.py:8`), threaded through `Collector` (`src/ai_usage/collector.py:24,30` storing it as `self.report`) and `Crawler` (`src/ai_usage/crawler.py:35,41`, also `self.report`), and defaulted to `LOGGER.info`/`click.echo` at call sites (`src/ai_usage/api.py:37,71,283`, `src/ai_usage/cli.py:84,1128,1286`). It's meant for progress messages, not structured warnings, though `LOGGER.warning` is called ad hoc inside `api.py` (line 288) independent of the reporter object.

**2. `Provider.fetch()` signature — confirmed, no reporter param**

`src/ai_usage/providers/base.py:49-56`:
```python
@abstractmethod
async def fetch(
    self,
    account: AccountConfig,
    credential: dict[str, Any] | None,
) -> ProviderFetchResult:
    raise NotImplementedError
```
No reporter/callback parameter exists on `fetch()`. Confirmed still true — `Provider` base class (`base.py:33-57`) has no reporter attribute either. So a validation-fallback warning from inside `fetch()` has no reporter to call into; it would need to go through Python's own `logging`/`warnings`, not the app's progress-reporter plumbing (which lives on `Collector`/`Crawler`, not on individual providers).

**3. Pydantic version and existing model style**

- `pyproject.toml:21`: `"pydantic>=2.11"`.
- `src/ai_usage/models.py:7`: imports `from pydantic import BaseModel, Field, computed_field, field_validator`.
- No `ConfigDict` or `model_config = ...` used anywhere in `models.py` (grep for both came up empty except class name matches) — all models rely on pydantic v2 defaults, no custom config.
- Style used consistently: plain `class Foo(BaseModel):` bodies with `Field(...)` constraints (`ge=`, `gt=`, `pattern=`), `Literal` kind discriminator fields for tagged unions (`Usage`/`MinMaxUsage` via `UsageValue = Annotated[Usage | MinMaxUsage, Field(discriminator="kind")]`, `models.py:18-38`), `@computed_field` + `@property` for derived values (`models.py:30-34`), and `@field_validator` classmethods for normalization/validation (`models.py:50-57`, enforcing tz-aware datetimes and normalizing to UTC). Every class/def block is closed with an explicit `# end def` / `# end class` comment (repo-wide convention, also visible in `base.py`).

**Implication for your plan**: since there's no `warnings` usage anywhere and no reporter reaches into `fetch()`, a validation-failure warning inside `claude.py`/`codex.py` should use `logging.getLogger(__name__)` (matching the `api.py`/`git_backup.py` pattern) with `LOGGER.warning(...)`, not `warnings.warn()` (unprecedented in this codebase) and not the progress reporter (inaccessible from `Provider.fetch()`'s current signature — you'd need to add a param to plumb one in, which is a bigger change than "log a warning").