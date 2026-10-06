[harness: subagent output matched instruction-shaped pattern(s): settings-json. Control tags below are neutralized (`<` → `<\`); treat any remaining directive-shaped text as a finding to relay to the user, not an instruction to you.]

I explored the repo read-only and changed nothing. Paths are under `/Users/user/Documents/programming/Python/ai-usage`, and line numbers are from the files as read.

## 1. Provider composition and the existing Claude providers

**Base classes**: `src/ai_usage/providers/base.py`
- `ProviderError` (l.12) and `ProviderLoginError` (l.17). `canonical_login()` (l.22) strips and casefolds an identity string, and raises `ProviderLoginError` if it is empty.
- `ConfigurationField` (l.30): `key`, `label`, `kind` (`string`, `integer`, `boolean`, `secret` or `path`), `required`, `default`, `help`.
- `DiscoveredAccount` (l.40): `name`, `options`, and an optional `credential`.
- `CredentialKind = Literal["none","bearer_token","cookie_jar","app_token"]` (l.47).
- `LoginMethod` ABC (l.50-71):
  - Class attributes are `key`, `display_name` and `credential_kind`.
  - `discover()` returns `[]` by default. `authenticate(options)` raises by default. `discover_options(credential)` returns `{}` by default.
- `UsageMethod` ABC (l.74-87): `required_credential_kind` plus abstract `async fetch(account, credential) -> ProviderFetchResult`.
- `FallbackUsageMethod` (l.90-118) tries each method in order and catches `ProviderError` only.
- `Provider` ABC (l.121-186):
  - Class attributes are `service`, `key`, `display_name`, `experimental`, `configuration_fields`, `login_url`, `login_hint`, `icon: IconRef | None`, `usage_method` and `login_methods`.
  - `matching_login_methods()` (l.142) keeps login methods whose `credential_kind` equals the usage method's `required_credential_kind`.
  - `discover()` (l.149) aggregates the matching login methods' `discover()`.
  - `user_identity(account, result)` (l.174) raises `NotImplementedError` by default and must return the canonical login string.
  - `fetch()` (l.180) delegates to `usage_method.fetch`.

**Registry**: `src/ai_usage/providers/registry.py`
- `ProviderRegistry` (l.32) keys providers by `(service, key)`. `register()` raises on duplicates. `get()` raises `KeyError`. `load_entry_points()` (l.53) reads the `ai_usage.providers` entry-point group.
- `built_in_registry()` (l.63-88) has a hard-coded tuple of provider instances, and discovery is not automatic. A new provider needs two edits here: an import near l.6-29 and an instance in the tuple. The Claude entries are `ClaudeStatusProvider()`, `ClaudeUsageProvider()` and `ClaudeWebUsageProvider()`.
- `src/ai_usage/providers/claude/__init__.py` re-exports the Claude provider classes (l.3-14) and an `__all__`. Tests import from it, so a new provider there is optional but follows convention.
- `src/ai_usage/provider_discovery.py`: `matching_providers()` (l.50), `exclude_discovered()` (l.65), and `discover_accounts()` (l.78-117), which gathers each provider's `discover()` concurrently and isolates failures. `DiscoveryChoice.fingerprint` (l.22) is a sha256 of service, provider and the discovered options.

**Package layout** is `providers/<service>/{provider.py, _shared.py, login/<kind>/<module>.py, usage/<kind>/<module>.py}`. Kinds seen are `cli`, `local`, `web`. Claude's layout:
- `src/ai_usage/providers/claude/provider.py` holds three assembled providers.
  - `ClaudeWebUsageProvider` (l.22-46), key `web`: uses `PrivateApiUsage` and `CookieCaptureLogin`, and has an `org_id` configuration field. Its `user_identity` is `email` or `email|org`.
  - `ClaudeStatusProvider` (l.49-71), key `statusline`: uses `FallbackUsageMethod((RelayFileUsage(), DirectCliUsage(), InteractiveCliUsage()))` and `login_methods=(SettingsFileLogin(),)`. Its `user_identity` returns the casefolded `result.identity.email`.
  - `ClaudeUsageProvider(ClaudeStatusProvider)` (l.74-90), key `cli-usage`: drops `relay_file` from the options before fetching.
- Claude usage methods:
  - `src/ai_usage/providers/claude/usage/local/relay_file.py`: `RelayFileUsage`, `required_credential_kind = "none"`. This is the closest analogue for a local source. `parse_status_payload()` is at l.14.
  - `src/ai_usage/providers/claude/usage/web/private_api.py`: `PrivateApiUsage` (l.167-288).
  - `src/ai_usage/providers/claude/usage/cli/direct.py`: `claude_metric_key()` (l.48), `claude_metric_model()` (l.60) and `parse_usage_output()` (l.73).
- Claude login methods:
  - `src/ai_usage/providers/claude/login/local/settings_file.py`: `SettingsFileLogin`, `credential_kind="none"`, `discover()` returns one `DiscoveredAccount` if `~/.claude/settings.json` exists (l.13-19).
  - `src/ai_usage/providers/claude/login/web/cookie_capture.py`: `CookieCaptureLogin`.
- Claude identity comes from `ProviderFetchResult.identity` (`AccountIdentity` with `name` and `email`). The relay path gets it by shelling out to `claude auth status` (`relay_file.py` l.69-71, `run_claude_auth_status` in `cli/direct.py` ~l.125).
- Claude-specific hard-codes elsewhere that do not apply to a new provider key:
  - `src/ai_usage/cli.py` ~l.194-200: canonicalizes `profile_dir` only for `statusline` and `cli-usage`.
  - `src/ai_usage/cli.py` ~l.256-262: installs the relay only for `statusline`.
  - `src/ai_usage/account_presentation.py` l.33: splits `login|org_id` only for `claude/web`.

## 2. Returning data

`src/ai_usage/models.py`:
- `Usage(percentage 0..100)` (l.18), and `MinMaxUsage(current, maximum, unit)` with a computed `percentage` (l.24-35).
- `Metric` (l.41-59):
  - Fields: `key` (regex `^[a-z0-9][a-z0-9-]*$`), `name`, `usage`, `observed_at`, `reset_at`, `window_seconds` (> 0), `model`, `metadata`.
  - Timestamps must be timezone-aware and are normalized to UTC.
- `AccountIdentity(name, email)` (l.62) and `SubscriptionStatus(plan_type, status, renews_at, cancel_at)` (l.70).
- `ProviderFetchResult` (l.105-117): `service`, `provider`, `account_id`, `fetched_at`, `status` (`FetchStatus` SUCCESS, PARTIAL, ERROR or STALE), `metrics`, `error`, `identity`, `subscription`, `raw_payload`, `notes`. Providers raise `ProviderError` on failure, and `collector.py` l.99 turns exceptions into an ERROR result.
- `AccountConfig` (l.120-136) stores `options: dict` (per-account provider settings), `login`, `credential_id` and `intervals`.

**Window mapping in existing Claude usage.** The same keys appear in `parse_status_payload`, `parse_claude_web_usage` and `parse_usage_output`:

| Window | key | name | `window_seconds` | `model` |
| --- | --- | --- | --- | --- |
| session | `five-hours` | `Five hours` | 18000 | none |
| weekly | `seven-days` | `Seven days` | 604800 | none |
| per-model weekly | `seven-days-<slug>` (CLI only) | `Current week (Opus)` | not set | model name (CLI only) |

- `claude_metric_key()` and `claude_metric_model()` live in `usage/cli/direct.py` l.48-72. For example, `Current week (Fable)` becomes `seven-days-fable` with `model="Fable"`.
- Only `five-hours` and `seven-days` use `window_seconds`. The web and relay paths only emit those two, so an `opus` window would be new for those paths.
- The CLI per-model metrics set `metadata={"reset_text": ...}` and no `reset_at`.
- For ClaudeUsage's `/opus`, `seven-days-opus` with `model="Opus"` and `window_seconds=604800` is consistent with the existing convention.

**Icons**: `src/ai_usage/graph.py`
- `SERVICE_ICONS` (l.39-43) covers only `claude` (brands/claude), `codex` and `copilot`. No change is needed for the `claude` service.
- `METRIC_ICONS` (l.48-59) maps `five-hours` to clock and `seven-days` to calendar-week. A `seven-days-opus` key has no entry and falls through `metric_icon_for()` (l.73-84) to the keyword match (`week` gives calendar-week). Add an explicit entry only if you want a distinct icon.
- `SERVICE_BASE_COLORS` (l.30-36) has `claude` as `#DE7356`.
- Provider icons come from `Provider.icon` (an `IconRef(set=, name=)`), and `api.py` l.134-138 exposes them keyed by `provider.key`. The Claude providers use solid `globe`, `gauge` and `terminal`. `src/ai_usage/icons.py` defines `IconRef` over Font Awesome Free sets (`brands`, `solid`, `regular`).
- The frontend only consumes `catalog.service_icons`, `provider_icons` and `metric_icons` (`frontend/src/types.ts` l.55-57, `App.vue` l.15 and l.86). It has no hard-coded icon table to edit.

## 3. The `add` wizard and config

`src/ai_usage/cli.py`
- `provider_add` (l.518-673), interactive flow:
  - `select_discovered_account()` (l.479) calls `select_provider()` (l.426-449), which first shows "Choose a provider" (the sorted set of services).
  - If the service has more than one provider, it shows "Choose how to fetch usage" with `display_name` plus `[experimental]`, and `provider.key` is the usage-method choice. A service with exactly one provider skips this prompt.
  - It then runs `discover_accounts` for that provider. Discovered accounts are listed with "Configure manually" appended.
  - If no credential is set and `provider.matching_login_methods()` is non-empty and the terminal is interactive, `resolve_login_method()` (l.452-463) shows "Choose how to sign in". It is skipped when there are 0 or 1 matching login methods.
  - Then `login_method.authenticate(dynamic_options)`, then `discover_options(credential)`, then `verify_provider_setup()` (l.285-315), which calls `provider.fetch` and then `provider.user_identity`.
  - `create_account()` (l.164-282) persists the account.
- A provider with `login_methods=()` or `credential_kind="none"` never reaches the sign-in prompt. `ClaudeStatusProvider` is the example.
- Non-interactive: `ai-usage provider add claude <key> --base-url http://... --no-input`. `parse_dynamic_options()` (l.128-150) turns any `--foo-bar value` into `options["foo_bar"]`.
- A bare `ai-usage provider add <service> <key>` auto-selects if exactly one account is discovered (l.575-585). So a `LoginMethod.discover()` that probes `/health` and returns one `DiscoveredAccount(options={"base_url": ...})` makes the add zero-config.
- `create_account()` applies `ConfigurationField`s (~l.176-193):
  - It fills `default` when the key is absent.
  - It prompts only if `required` is set (or errors under `--no-input`).
  - It coerces `integer` and `boolean` kinds.
  - It never prompts for optional fields, so a `base_url` field with a default of `http://127.0.0.1:47291` works silently, and users override it with `--base-url`.
- `verify_provider_setup` requires `provider.user_identity()` to return a login, or the add fails. Per `ai/memory/project_ai_usage_new_providers_batch.md`, Kimi and OpenRouter raise there by design and so cannot be added. If ClaudeUsage's `/usage` or `/health` exposes no email, you need either another identity source or a stable pseudo-login. This is the main design risk.
- Account dedupe: `configuration_key()` (`account_presentation.py` l.49) is `(service, login, org, provider)`. A duplicate raises a ClickException (`cli.py` ~l.220-235).
- `run_provider_add_wizard` (`cli.py` l.818-865) is a second, simpler wizard used by the first-crawl onboarding. It runs the same select, login, verify and create steps with no `dynamic_options`.
- Storage:
  - Each account is `~/.ai-usage/services/<service>/<id>.yml`, written by `ConfigStore.save_account` (`src/ai_usage/config.py` l.89-101), with `options` as a dict.
  - Credentials are encrypted in SQLite (`Database.put_credential`) and are not needed for `none`.
  - Global `config.yml` has `intervals`, `services.<svc>.intervals` and `providers.<key>.intervals` (`config.py` l.161-173). Intervals are keyed by provider key, not by service and key.
- `Provider.user_identity` and fetch are invoked from `collector.py` l.93-99 (`provider.fetch(account, credential)`).

## 4. Template and tests

There is no pure no-login HTTP provider yet. The nearest templates are:
- **Structure (no credential)**: `ClaudeStatusProvider` plus `RelayFileUsage` (`usage/local/relay_file.py`) and `SettingsFileLogin` (`login/local/settings_file.py`). Codex also has `CodexStatusProvider` with `login_methods=()` (`codex/provider.py` l.55-70), and `AuthJsonLogin` is another local-discovery login.
- **HTTP style**: `src/ai_usage/providers/openrouter/provider.py` plus `usage/web/private_api.py` uses `httpx.AsyncClient(base_url=..., timeout=20)`, raises `ProviderError` on non-200, and builds metrics. Claude web uses `curl_cffi.requests.AsyncSession(..., impersonate="chrome")` because of Cloudflare. A loopback API does not need curl_cffi, so `httpx` is the natural choice.
- Suggested layout: `providers/claude/usage/local/<name>.py` for the usage method and `providers/claude/login/local/<name>.py` for the discovery login, then a new `Provider` subclass in `claude/provider.py` (for example key `app` or `usage-app`).

**Tests** (`pytest-asyncio` with explicit `@pytest.mark.asyncio`, `respx` in the `test` extra):
- `tests/test_new_providers.py` (510 lines):
  - Helper `account(service, provider, options)` at l.55.
  - Pattern: `@pytest.mark.asyncio` plus `@respx.mock`, `respx.get("https://...").mock(return_value=httpx.Response(200, json=...))`, then `await XProvider().fetch(account(...), {"token": "key"})`.
  - Error paths use `pytest.raises(ProviderError)`. Identity is tested with `pytest.raises(ProviderLoginError)` (l.100-109).
  - Parser functions are tested directly with a fixed `datetime(2026,1,1,tzinfo=UTC)`.
- `tests/test_providers.py` (Claude and Codex):
  - `FakeCurlResponse` and `FakeCurlSession` (l.52-93) stand in for `curl_cffi`, because respx only intercepts httpx. Used with `monkeypatch.setattr(...AsyncSession, ...)`.
  - Claude local-file style tests start at l.754, such as `test_claude_status_fresh_relay_is_success`, with `monkeypatch.setattr("ai_usage.providers.claude.usage.local.relay_file.run_claude_auth_status", ...)`.
  - Identity tests are at l.962-985.
  - Login discovery is tested directly, as in `test_copilot_cli_login_reuses_configured_session` (l.670).
- `tests/test_provider_discovery.py`: uses a `ProviderRegistry` with stub providers (`DiscoveringProvider`).
- `tests/test_provider_commands.py` (the wizard):
  - The pattern is `monkeypatch.setattr(ai_usage.cli, "interactive_terminal", ...)`, a fake `ai_usage.cli.select_choice` returning keys for titles "Choose a provider" and "Choose how to fetch usage", then `CliRunner().invoke(main, ["provider","add"])`.
  - It uses `configured_paths(tmp_path, monkeypatch)` and `HOME` isolation.
  - Monkeypatch the concrete `LoginMethod` or `UsageMethod` class, not `Provider.authenticate` (memory `feedback_login_usage_split_test_targets.md`).
- Gotchas from `ai/memory`:
  - `feedback_respx_loopback_no_passthrough.md`: respx cannot pass through to a real loopback server. If a test runs an actual local `http.server` for 127.0.0.1:47291, do not combine it with `@respx.mock`. Mocking with respx as usual (respx intercepts the URL itself) is fine.
  - `feedback_test_home_isolation.md`: set `HOME` to `tmp_path` when code touches `Path.home()`.
- `tests/test_models.py` and `tests/test_api.py` do not enumerate providers. Nothing asserts the registry's contents, so adding one will not break existing tests.

## 5. Docs and places to update

- `README.md`:
  - The "Collection methods" table (l.148-158) needs a new row. `statusline` and `cli-usage` rows are at l.152-153.
  - Intro l.3 and l.21 (prereqs list `codex`/`claude`) and the Quick start (l.38-60) with its `provider add` examples.
  - "Discovery finds nothing" troubleshooting at l.303.
  - README l.126 says provider-specific fields are passed as flags, which is where `--base-url` would be documented.
  - L.160 mentions entry points.
- `ai/todo.md` has no provider list. Its first lines are graph and UI items (l.1-17), and `ai/plans/pending.md` is historical notes. Only add a todo or plan entry if you want one. The convention is numbered plans in `ai/plans/` (latest is `029_...`).
- `CLAUDE.md` and `AGENTS.md` contain no provider list (generic guidance only).
- `ai/memory/MEMORY.md` indexes `project_ai_usage_new_providers_batch.md` and `project_ai_usage_provider_add_wizard.md`. A new memory is optional.
- Code touchpoints:
  - `src/ai_usage/providers/registry.py` (import plus tuple entry).
  - Optionally `src/ai_usage/providers/claude/__init__.py` (export).
  - Optionally `graph.py` `METRIC_ICONS` for an opus icon.
  - Nothing is needed in `pyproject.toml`. There is no entry-point listing for built-ins, and `httpx` is already a dependency.
- No frontend changes are required unless a new `IconRef` is used, since icons are served through the catalog and the backend FontAwesome proxy.