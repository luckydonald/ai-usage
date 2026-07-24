I have enough. Let me report.

## Summary

### 1. Command flow — `provider add`

File: `/home/user/git/luckydonald/ai-usage/src/ai_usage/cli.py`

- Command definition: `provider_add` at cli.py:472-622 (`@provider_app.command("add", ...)`).
- Non-interactive/no-args path: if `service`/`provider_key` missing and terminal isn't interactive, just prints discovery choices via `print_discovery_choices` (cli.py:495-507, defined cli.py:392-413) and returns — no wizard.
- Interactive selection: `select_discovered_account` (cli.py:429-469) is the core picker:
  - Calls `discover_or_error` → `discover_accounts(registry, service, provider_key)` (cli.py:416-426) to get `DiscoveryChoice` list (already-found local accounts, e.g. from config files on disk).
  - Builds `SelectionChoice` list (`discovered-{i}`) plus a trailing `"manual"` "Manually configure other…" entry, shown via `select_choice("Choose an account to add", options)` (cli.py:442-447).
  - If user picks "manual", it lists all remaining provider adapters (`service/key: display_name [experimental]`) via a second `select_choice("Choose a provider adapter", manual_options)` (cli.py:454-467) — this is effectively the "pick a provider" step.
- Back in `provider_add`: resolves `resolved_service`/`resolved_provider` from either the discovered choice or the manually chosen provider (cli.py:553-561).
- Credential resolution (cli.py:562-587):
  - From `--secret-json`/`--secret-file` (`parsed_credential`, cli.py:382-388, using `credential_payload` cli.py:144-152).
  - Else from the discovered account's stored credential (`selected.account.credential`).
  - Else, if `provider.login_url` set and terminal interactive, calls `provider.authenticate(dynamic_options)` (an OAuth/browser login flow) — echoes `login_hint` if present (cli.py:567-582).
  - After credential is obtained, calls `provider.discover_options(credential)` to auto-fill any config options (cli.py:583-587).
- Verification: builds a throwaway `AccountConfig` (probe) and calls `verify_provider_setup(provider, probe_account, credential)` (cli.py:276-303), which internally calls `provider.fetch(...)` then `provider.user_identity(account, result)` to get the canonical `login` string.
- Persistence: `create_account(...)` (cli.py:155-273) — see below.
- No prompts library step for "required configuration_fields" happens in `provider_add`'s main path itself; that prompting (`click.prompt`) happens inside `create_account` (cli.py:169-178) for any `ConfigurationField` marked `required` with no default and not yet filled — shown as plain `click.prompt(field.label, hide_input=field.kind=="secret")`.

There's also a simpler wizard variant: `run_provider_add_wizard` (cli.py:750-783), used from `run_first_crawl_wizard` (cli.py:786-817, itself called from `ensure_ready_to_crawl` cli.py:820-833) — same `select_discovered_account` → `verify_provider_setup` → `create_account` flow, no CLI-flag path.

Related standalone commands:
- `provider_discover` (cli.py:625-640) — just lists discoverable local accounts, no add.
- `provider_login` (cli.py:643-707) — re-authenticates an existing account (`provider.authenticate` → `provider.fetch` → `provider.user_identity` → persists via `runtime.config.save_account`).

### 2. Storage model

- Account model: `AccountConfig` in `/home/user/git/luckydonald/ai-usage/src/ai_usage/models.py:120-136`:
  ```
  id, service, provider, name, enabled=True, removed_at, credential_id,
  discovery_fingerprint, login, options: dict[str, Any] = {}, colors: dict[str,str] = {},
  intervals: dict[str,int] = {}, hosts: list[tuple[str,str]] | None, identity: AccountIdentity | None,
  subscription: SubscriptionStatus | None
  ```
  Note: no `credential` field directly — credentials are stored separately (encrypted) in the SQLite database via `runtime.database.put_credential(provider_key, account_name, credential)` (cli.py:235, cli.py:684-686), and only a `credential_id` reference is kept on `AccountConfig`.
- `options` field holds provider-specific dynamic config (from `ConfigurationField`s / `discover_options`).
- `service`/`provider` fields identify which registered `Provider` (service namespace + key) the account belongs to.
- Creation/persistence goes through `runtime.config.create_account(...)` / `runtime.config.save_account(...)` (`ConfigStore`, referenced but defined elsewhere, e.g. `ai_usage/config.py` — not read in this pass but called at cli.py:251-258, 265, 270, 699).

### 3. Prompt/wizard library

No questionary/InquirerPy/rich-prompt usage found. The project uses a custom **Textual**-based single-select screen:
- `/home/user/git/luckydonald/ai-usage/src/ai_usage/provider_tui.py`: `SelectionChoice` dataclass (key/label/detail) and `select_choice(title, choices) -> str | None` (line 58-63), backed by a `SelectionApp(App[str|None])` using Textual's `OptionList` (lines 19-55). Cancel via Escape returns `None`.
- Plain `click.prompt`/`click.confirm`/`click.echo` are used for simple text/secret input and yes/no confirmations (e.g. cli.py:177, cli.py:718).
- Multi-step wizards are hand-rolled loops chaining multiple `select_choice` calls (e.g. `select_discovered_account` cli.py:429-469 — two chained selects; `run_first_crawl_wizard` cli.py:786-817 — `while True` loop with nested selects).

For a new "provider add" wizard with multiple selection steps, the pattern to reuse is: build `SelectionChoice` lists, call `await select_choice(title, options)` (must be awaited inside `asyncio.run(execute())`), handle `None` as cancel, and chain steps as needed (as `select_discovered_account` does for account-then-provider).

### 4. How provider metadata is surfaced

- Provider metadata fields (base class): `/home/user/git/luckydonald/ai-usage/src/ai_usage/providers/base.py:47-55` — `service`, `key`, `display_name`, `experimental`, `configuration_fields: tuple[ConfigurationField,...]`, `login_url`, `login_hint`, `icon`.
- `ConfigurationField` model: base.py:30-37 (`key, label, kind, required, default, help`).
- There is no dedicated `provider list`-of-adapters/menu command showing all registered providers' `display_name`s independent of add. The closest is:
  - `print_discovery_choices` (cli.py:392-413), which prints "Manual provider adapters:" as `{service}/{key}: {display_name}{[experimental]}` for providers not already discovered — invoked by `provider_add` (non-interactive path) and `provider_discover`.
  - The "manual" branch of `select_discovered_account` (cli.py:454-467) builds an interactive Textual menu of `service/key` labeled with `display_name` (+ "[experimental]") for provider selection.
  - `provider_list` (cli.py:931-939) / `print_accounts` (cli.py:844-861, not fully read but referenced) lists already-configured **accounts**, not the registry of available providers.
- Provider registry itself (`ProviderRegistry`, `built_in_registry`, `matching_providers`, `exclude_discovered`) is imported into cli.py but defined elsewhere (likely `provider_registry.py`) — not inspected in this pass; would be worth reading if you need to enumerate "all registered providers" for a new wizard menu.