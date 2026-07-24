# Build the new `provider add` wizard (service → usage-method → login-method)

## Context

The `providers/` login/usage split landed already (commit `da98173`): `Provider` is now a composition of one `usage_method: UsageMethod` (the registry identity) plus `login_methods: tuple[LoginMethod, ...]` filtered by `credential_kind`. What's left from that plan is the actual CLI wizard rewrite — today `cli.py`'s `select_discovered_account` still treats "pick a provider" as one flat list of `service/key: display_name` strings (the "Manually configure other…" branch), with no separate step for service vs. usage-method vs. login-method, and no way to choose between alternative login methods (today always silently takes `matching_login_methods()[0]`). Goal: make `provider add`/`provider login` walk the three-step chain the base-class redesign was built for, and only add real complexity where the data actually varies (no login-method prompt when there's only one candidate, no service prompt when a service arg was already given, etc).

## What exists to build on

- `src/ai_usage/providers/base.py`: `Provider.matching_login_methods()` (already public), `Provider.discover()`/`authenticate()`/`discover_options()` (already delegate to `matching_login_methods()[0]`, unchanged for the ≤1-candidate case — which is every built-in provider today).
- `src/ai_usage/provider_tui.py`: `SelectionChoice(key, label, detail="")` + `async select_choice(title, choices) -> str | None` (Textual modal, `None` = cancelled/empty). Reuse as-is, no new dependency.
- `src/ai_usage/provider_discovery.py`: `matching_providers(registry, service=None, provider=None)`, `discover_accounts(registry, service, provider)`, `DiscoveryChoice`, `DiscoveryFailure`, `exclude_discovered` — **no changes needed here**, it already supports being scoped to one `(service, key)` pair, which is exactly what the new flow needs.
- `src/ai_usage/cli.py` functions in scope: `select_discovered_account` (429-469), `provider_add` (472-622), `provider_discover` (625-640), `provider_login` (643-707), `run_provider_add_wizard` (750-783), `run_first_crawl_wizard` (786-817), plus the shared tail `verify_provider_setup` (276-303) and `create_account` (155-273) — **not changed**, they operate on an already-resolved `(service, provider_key, credential, options)` regardless of how those were obtained.
- `print_discovery_choices` (392-413) — small display change only (group by service).

## Design

### 1. New helper: pick a provider in two steps

Replace the "manual provider adapter" flat list inside `select_discovered_account` with a new `select_provider(registry: ProviderRegistry) -> Provider | None`:

1. `services = sorted({impl.service for impl in registry.providers.values()})` → `select_choice("Choose a provider", [SelectionChoice(s, s) for s in services])`. `None` return (Escape) → propagate `None`.
2. `candidates = matching_providers(registry, service=chosen_service)` → `select_choice("Choose how to fetch usage", [SelectionChoice(p.key, f"{p.display_name}{' [experimental]' if p.experimental else ''}") for p in candidates])`. `None` → propagate `None`.
3. Return `registry.get(chosen_service, chosen_key)`.

If `matching_providers(registry, service=chosen_service)` has exactly one candidate, skip step 2's prompt and auto-select it (mirrors the plan's "single-match auto-select" rule, same UX principle applied here to the usage-method step too, not just login-method).

### 2. `select_discovered_account` rewrite

Current shape (429-469): discover across the given `service`/`provider_key` filter (already narrow if CLI args were given, `None`/`None` i.e. everything otherwise) → list discovered accounts → "manually configure other…" trailing entry → on that, list *all* remaining provider adapters flatly.

New shape:
1. If `service is None or provider_key is None` (interactive, no CLI args): call `select_provider(registry)` first. If it returns `None`, the whole flow is cancelled. Otherwise `service, provider_key = provider.service, provider.key`.
2. Now always call `discover_or_error(registry, service, provider_key)` — scoped to exactly the one resolved provider (same call already exists, just always narrow now instead of sometimes-broad).
3. If discovered accounts exist, offer them via `select_choice("Choose an account to add", ...)` same as today, plus a trailing "Configure manually" entry (no longer "…other provider", since the provider is already fixed) — picking manual just proceeds with no `DiscoveredAccount`, same as today's manual path but scoped to the already-resolved provider instead of prompting for one again.
4. If no discovered accounts, skip straight to the manual path (no empty/degenerate select prompt).

Net effect: two Textual prompts (service, usage-method) run *before* discovery instead of one flat prompt covering both "which account" and "which provider" at once — matches the plan's step 1/2. When `service`/`provider_key` were passed as CLI args (`provider_add codex app-server ...`), behavior is unchanged (no new prompts, discovery was already scoped).

### 3. Login-method selection (only prompts when it matters)

Add a small helper used wherever a credential must be resolved (`provider_add`'s `execute()` around 562-587, `run_provider_add_wizard` 750-783, `provider_login` 643-707):

```python
async def resolve_login_method(provider: Provider) -> LoginMethod | None:
    matching = provider.matching_login_methods()
    if len(matching) <= 1:
        return matching[0] if matching else None  # existing behavior, 0 or 1 case unchanged
    choices = [SelectionChoice(m.key, m.display_name) for m in matching]
    key = await select_choice("Choose how to sign in", choices)
    return next((m for m in matching if m.key == key), None) if key else None
```

Call sites that currently do `await provider.authenticate(dynamic_options)` / `await provider.discover_options(credential)` (cli.py 573, 584, 659, 690 region) get a preceding `method = await resolve_login_method(provider)` and, when `method is not None`, call `method.authenticate(...)`/`method.discover_options(...)` directly instead of the `Provider`-level delegators (which only ever reach `matching_login_methods()[0]`). When `method is None` (0 matching methods — e.g. Copilot billing, which expects an externally-supplied credential/flag), behavior is unchanged: fall through to the existing `--secret-json`/`--secret-file`/manual-prompt path.

Since every built-in provider today has 0 or 1 matching login methods, this step is a no-op prompt-wise right now — it's the seam the plan asked for ("bonus points if the login could later be switched out with another"), not speculative dead code: `resolve_login_method` is on the hot path of every add/login call, just short-circuits until a provider actually ships ≥2 alternatives for the same `credential_kind`.

### 4. Display grouping (`print_discovery_choices`, `provider_discover`)

Change the "Manual provider adapters:" listing (392-413) from a flat `{service}/{key}: {display_name}` per line to grouped-by-service:
```
Manual provider adapters:
  claude:
    web: Claude private web API
    statusline: Claude status line with /usage fallback
    cli-usage: Claude /usage
  codex:
    ...
```
Group via `itertools.groupby` or a plain dict after sorting `matching_providers(registry)` by `(service, key)` (already the sort order `matching_providers` returns).

### 5. `provider_login` (643-707)

Same shape as `provider_add`'s credential-resolution tail: insert `resolve_login_method(provider)` before the existing `provider.authenticate(account.options)` call (region ~659); everything after (fetch, `user_identity`, persist via `runtime.database.put_credential`) is unchanged.

### Not touched

- `verify_provider_setup`, `create_account`, `DiscoveryChoice`/`discover_accounts`/`matching_providers`/`exclude_discovered`, all 9 built-in `Provider`/`LoginMethod`/`UsageMethod` classes, `AccountConfig` model. This is purely a `cli.py` (+ maybe `provider_tui.py` if a new dataclass is genuinely needed for return values — check during implementation whether `select_discovered_account`'s new return shape needs a small dataclass or can keep reusing what's there) orchestration change.
- The `login_url`/`login_hint` duplication between `Provider` (drives `cli.py`'s current window-opening prompt text) and each `LoginMethod` (drives the method's own internal `capture_cookies_via_webview` call) is a known minor overlap, not unified in this pass — out of scope, doesn't block the wizard.

## Implementation steps

1. Add `select_provider(registry)` and `resolve_login_method(provider)` helpers to `cli.py` (near `select_discovered_account`/`discover_or_error`).
2. Rewrite `select_discovered_account` per section 2.
3. Wire `resolve_login_method` into `provider_add`'s `execute()` credential-resolution block, `run_provider_add_wizard`, and `provider_login`.
4. Update `print_discovery_choices` grouping per section 4.
5. Run `uv run pytest tests/test_provider_commands.py tests/test_provider_discovery.py -q`; fix any test expecting the old flat "Manual provider adapters:" format or the old single-prompt discovered-account flow (search test assertions for `"Manual provider adapters:"`, `"Choose an account to add"`, `select_choice` call-count assertions).
6. Manually exercise `ai-usage provider add` for: a no-login provider (`codex cli-status`), a cookie-login provider (`codex web`), and confirm the two new prompts (service, then usage-method) appear before account/manual selection, and that passing `provider add codex app-server ...` positionally still skips both prompts.

## Verification

- `uv run pytest tests/ -q` — full suite; expect the same pre-existing 5 failures as before (`test_api_catalog_latest_and_series`, 4× `test_progress.py`), zero new failures.
- Manual run of `ai-usage provider add` (interactive) confirming the chained prompts and that `--no-input`/flag-only invocations remain non-interactive and unchanged.
