# `provider add` wizard: service → usage-method → login-method

## Context

Login/usage `Provider` split already landed (commit `da98173`). Left: `cli.py`'s add/login flow still picks a provider as one flat `service/key: display_name` list and always silently uses `matching_login_methods()[0]`. Rework it to chain: pick service → pick usage-method → resolve login-method (prompt only if >1 candidate).

## Changes

### 1. `select_provider(registry) -> Provider | None` (new helper in `cli.py`)

1. `services = sorted({impl.service for impl in registry.providers.values()})` → `select_choice("Choose a provider", [SelectionChoice(s, s) for s in services])`. `None` → return `None`.
2. `candidates = matching_providers(registry, service=chosen_service)`. If exactly one, auto-select it (no prompt). Else `select_choice("Choose how to fetch usage", [SelectionChoice(p.key, f"{p.display_name}{' [experimental]' if p.experimental else ''}") for p in candidates])`. `None` → return `None`.
3. Return `registry.get(chosen_service, chosen_key)`.

### 2. `select_discovered_account` (cli.py:429-469) rewrite

- If `service is None or provider_key is None`: call `select_provider(registry)` first; cancel propagates. Set `service, provider_key` from the result.
- Then `discover_or_error(registry, service, provider_key)` — always scoped to the one resolved provider now (previously sometimes broad).
- If discovered accounts exist: `select_choice("Choose an account to add", ...)` + trailing "Configure manually" entry (provider already fixed, no longer "…other provider").
- If none discovered: skip straight to manual, no empty prompt.
- When `service`/`provider_key` came in as CLI args, behavior is unchanged (no new prompts).

### 3. `resolve_login_method(provider) -> LoginMethod | None` (new helper)

```python
async def resolve_login_method(provider: Provider) -> LoginMethod | None:
    matching = provider.matching_login_methods()
    if len(matching) <= 1:
        return matching[0] if matching else None
    choices = [SelectionChoice(m.key, m.display_name) for m in matching]
    key = await select_choice("Choose how to sign in", choices)
    return next((m for m in matching if m.key == key), None) if key else None
```

Wire into every credential-resolution call site: `provider_add`'s `execute()` (~562-587), `run_provider_add_wizard` (750-783), `provider_login` (~659). When a method is resolved, call `method.authenticate(...)`/`method.discover_options(...)` directly (not the `Provider`-level delegators, which only ever reach `matching_login_methods()[0]`). When `resolve_login_method` returns `None` (0 matches, e.g. Copilot billing's externally-supplied credential), fall through to the existing `--secret-json`/`--secret-file`/manual-prompt path unchanged.

Every built-in provider today has 0 or 1 matching login methods, so this is a no-op prompt-wise right now — it's the seam for a provider that later ships ≥2 alternatives per `credential_kind`, not speculative dead code (it's on the hot path of every add/login call).

### 4. `print_discovery_choices` (cli.py:392-413) — group by service

Change the flat `{service}/{key}: {display_name}` listing to grouped-by-service (sort `matching_providers(registry)` by `(service, key)`, group with `itertools.groupby` or a plain dict):
```
Manual provider adapters:
  claude:
    web: Claude private web API
    statusline: Claude status line with /usage fallback
  codex:
    ...
```

### Not touched

`verify_provider_setup`, `create_account`, `provider_discovery.py` (`discover_accounts`/`matching_providers`/`exclude_discovered`/`DiscoveryChoice`), all `Provider`/`LoginMethod`/`UsageMethod` classes, `AccountConfig`. Pure `cli.py` orchestration change (plus maybe a small dataclass in `provider_tui.py`/`cli.py` if `select_discovered_account`'s new return shape needs one — decide during implementation). The `login_url`/`login_hint` duplication between `Provider` and each `LoginMethod` stays as-is, out of scope.

## Implementation steps

1. Add `select_provider` and `resolve_login_method` to `cli.py`.
2. Rewrite `select_discovered_account` per section 2.
3. Wire `resolve_login_method` into `provider_add`, `run_provider_add_wizard`, `provider_login`.
4. Update `print_discovery_choices` grouping per section 4.
5. `uv run pytest tests/test_provider_commands.py tests/test_provider_discovery.py -q`; fix tests asserting the old flat "Manual provider adapters:" text or old single-prompt flow.
6. Manually exercise `ai-usage provider add` for a no-login provider (`codex cli-status`) and a cookie-login provider (`codex web`): confirm the two new prompts (service, usage-method) appear before account/manual selection, and that `provider add codex app-server ...` given positionally still skips both prompts.

## Verification

- `uv run pytest tests/ -q` — expect the same pre-existing 5 failures as before this whole effort (`test_api_catalog_latest_and_series`, 4× `test_progress.py`), zero new failures.
- Manual run of `ai-usage provider add` (interactive) confirming chained prompts; `--no-input`/flag-only invocations stay non-interactive.
