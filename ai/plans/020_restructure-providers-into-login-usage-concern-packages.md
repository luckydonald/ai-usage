# Restructure `providers/` into login/usage concern packages

## Context

`src/ai_usage/providers/` currently mixes two independent concerns inside one `Provider` class per file: **login** (how a credential/token is acquired — local file, browser+cookie capture, CLI token reuse) and **usage** (how the actual metrics API/CLI is called once a credential exists). Several providers already have multiple alternative login paths for the same usage call (e.g. Codex app-server: local `auth.json` file *or* browser cookie capture could both yield a usable credential) and multiple fallback usage mechanisms for the same login (e.g. Claude statusline: relay-file read → direct CLI → PTY-interactive CLI). Today these are tangled together inside single `fetch()`/`discover()` methods per provider file (`codex.py`, `copilot.py`, `claude/status.py`, `claude/api.py`), making it hard to see or reuse a login mechanism across providers, or reason about a usage mechanism independent of how the credential was obtained.

Goal: split login and usage into standalone, composable objects, organized as `providers/<provider>/login/<type>/<method>.py` and `providers/<provider>/usage/<type>/<method>.py`, with a thin per-provider `Provider` that just wires: which login method(s) can discover/produce a credential, and which usage method(s) actually call the API/CLI with that credential. Pure refactor — no behavior change, all existing tests must pass (with import paths updated).

## Key design point: usage is the identity, login is pluggable

The unique/registry identity of a "provider" in the old sense is the **usage** side (the crawler/parser calling a specific API or CLI/file) — that's what the one-account-per-login-identity dedup logic keys off (`user_identity`, merge-by-email/username). **Login is an auxiliary, swappable input**: several login mechanisms can produce a usable credential for the same usage method (e.g. a Bearer token for Codex's web API could come from a local CLI config file, an interactive browser cookie-capture, or being pasted in manually). So `usage/<type>/<method>.py` holds the "real" provider logic and is what `ProviderRegistry` keys on; `login/<type>/<method>.py` holds independent, in-principle-swappable ways to obtain a credential, selected by the user (or auto-discovered) at setup time, not hardcoded 1:1 to a usage method.

This also drives the intended `ai-usage provider add` wizard flow: pick provider (service) → pick usage category/method (`cli`/`api`/`web` → which parser, e.g. Codex `/usage` CLI vs Codex web API vs Codex app-server) → the tool now knows what credential shape that usage method needs (none, if it's a local CLI already logged in; a Bearer token; a cookie jar) → offer the compatible login methods for that need (local file reuse, interactive browser login, manual paste) → run the chosen login flow → assemble the account. No back-compat shims needed — this project owns every import site, so the old flat module names (`codex.py`, `copilot.py`, etc.) and old class names are freely renamed/dropped; there is no external consumer to preserve compatibility for.

## Design

### New base abstractions (`providers/base.py`)

Keep `Provider(ABC)`, `ProviderError`, `ProviderLoginError`, `ConfigurationField`, `DiscoveredAccount`, `canonical_login` as-is (public API used by `cli.py`, `collector.py`, `provider_discovery.py`, tests must not change).

Add two new small ABCs alongside:

- `LoginMethod(ABC)` — one way to obtain/discover a credential.
  - `credential_kind: str` class attr (e.g. `"none"`, `"bearer_token"`, `"cookie_jar"`) — declares what shape of credential this method produces, for matching against a usage method's need.
  - `discover() -> DiscoveredAccount | None` (optional, default returns `None`)
  - `authenticate(options) -> dict` (optional, default raises `ProviderLoginError`)
  - `discover_options(credential) -> dict` (optional, default returns `{}`)
- `UsageMethod(ABC)` — one way to fetch usage given a credential; this is the registry identity (service+key).
  - `required_credential_kind: str` class attr — what `LoginMethod.credential_kind` it needs (or `"none"` if self-contained, e.g. reading a local CLI's own session).
  - `fetch(account, credential) -> FetchResult` (abstract)

`Provider` becomes a small composition object: `Provider(usage_method: UsageMethod, login_methods: list[LoginMethod])`, `service`/`key`/`display_name` etc. sourced from `usage_method`. Its `discover/authenticate/discover_options` try the configured `login_methods` (filtered to matching `credential_kind`); `fetch` delegates straight to `usage_method.fetch`. This is what backs the `provider add` wizard: list `usage_method`s per service for step 2, then list `login_methods` whose `credential_kind == usage_method.required_credential_kind` for step 3.

`Provider.discover/authenticate/discover_options` become thin delegators to `self.login_method` (or first of `self.login_methods` that supports the call). `Provider.fetch` delegates to `self.usage_method`, or tries a list `self.usage_methods` in order (covers the Claude statusline relay→CLI→PTY fallback chain) — model this as a small `FallbackUsageMethod(UsageMethod)` helper in `base.py` that wraps an ordered list and tries each, so per-provider `fetch()` logic doesn't need custom looping code.

`user_identity` stays on `Provider` itself (it's about interpreting a fetch result/account, not a login or usage mechanism) — no move needed, matches explorer finding.

### Directory layout (per provider)

```
providers/
  base.py                      # Provider, LoginMethod, UsageMethod, FallbackUsageMethod, errors, DiscoveredAccount, ConfigurationField
  registry.py                  # unchanged wiring, only import paths updated
  claude/
    __init__.py                # re-exports (back-compat: ClaudeWebUsageProvider, ClaudeStatusProvider, ClaudeUsageProvider, install_status_relay, remove_status_relay, run_claude_auth_status, parsing helpers)
    _shared.py                 # claude_environment, claude_profile_path, canonical_claude_profile_dir, claude_default_profile (from claude_cli.py) — used by both login and usage code
    login/
      local/
        settings_file.py       # discover() via ~/.claude/settings.json  (was ClaudeStatusProvider.discover)
        auth_json.py            # (codex) local ~/.codex/auth.json probe, credential temp-file injection helper
      web/
        cookie_capture.py       # authenticate()+discover_options() via capture_cookies_via_webview (was ClaudeWebUsageProvider.authenticate/discover_options)
      cli/
        token_reuse.py          # (copilot) copilot_cli_credentials() local-file/env token reuse, modeled as a LoginMethod
    usage/
      web/
        private_api.py          # HTTP fetch via curl_cffi (was ClaudeWebUsageProvider.fetch + api.py parsing/payload models)
      local/
        relay_file.py           # read relay JSON file (was part of ClaudeStatusProvider.fetch)
      cli/
        direct.py                # run_claude_usage_direct (from claude_direct.py)
        interactive.py           # run_claude_usage (from claude_interactive.py, pexpect PTY)
    relay.py                    # install_status_relay/remove_status_relay stay here (setup-time CLI helper, not a LoginMethod/UsageMethod — called directly from cli.py)
    provider.py                 # ClaudeWebUsageProvider, ClaudeStatusProvider, ClaudeUsageProvider assembled from the above
  codex/
    __init__.py
    login/
      local/auth_json.py
      web/cookie_capture.py
    usage/
      web/private_api.py
      cli/app_server.py         # AppServerClient + CodexAppServerProvider usage logic
      cli/status_ptv.py         # run_codex_status PTY (was codex.py run_codex_status/CodexStatusProvider)
    provider.py                 # CodexWebUsageProvider, CodexAppServerProvider, CodexStatusProvider
  copilot/
    __init__.py
    login/
      cli/token_reuse.py        # copilot_cli_credentials, shared with claude? -> keep copilot-specific, no cross-provider sharing forced
      local/config_file.py      # discover() via ~/.copilot/config.json
    usage/
      web/billing_api.py        # CopilotBillingProvider.fetch (httpx GitHub billing API)
      web/quota_api.py          # CopilotStatusProvider.fetch (httpx copilot_internal/user) + parse_copilot_quota_payload
      web/entitlements.py       # PrivateWebProvider/CopilotEntitlementsProvider generic HTTP (from web.py)
    provider.py
  web.py                        # keep PrivateWebProvider generic base + CopilotEntitlementsProvider here if it's meant as a reusable cross-provider base, OR move PrivateWebProvider itself into providers/base.py as a generic UsageMethod-style helper — decide during implementation, low risk either way
```

Notes:
- `type` values used above: `local` (file/env read), `web` (browser/cookie or HTTP API — split into login/web = cookie capture, usage/web = HTTP API call), `cli` (subprocess, direct or PTY-interactive).
- Where a mechanism is truly identical across providers (e.g. `capture_cookies_via_webview` browser flow), keep the provider-specific glue (selectors, cookie names) in each provider's `login/web/cookie_capture.py`, but they all call the same shared `ai_usage/webview_login.py` helper — no need to further generalize that.
- Login-credential logic currently embedded inside `fetch()` (Codex app-server's temp `auth.json` write at codex.py:407-413, Copilot statusline's `copilot_cli_credentials()` call inside `fetch`) moves out: the credential dict handed to `UsageMethod.fetch` should already be fully resolved (temp file written, token reused) by the `LoginMethod`/orchestration step in `Provider`, not inline in the usage method.

### What changes at the edges (no back-compat kept)

- `providers/__init__.py` keeps exporting `ConfigurationField`, `Provider`, `ProviderError`, `ProviderRegistry`, `built_in_registry` — these are genuinely still the top-level public shape.
- Old class names (`ClaudeStatusProvider`, `CodexWebUsageProvider`, etc.) are not preserved as-is if the new composition model gives a better name — rename freely (e.g. towards `usage_method`/`login_method` instances rather than one big subclass per provider). Every import site is inside this repo (`registry.py`, `cli.py`, `collector.py`, `provider_discovery.py`, `tests/*`) and gets updated directly, not shimmed.
- `install_status_relay`/`remove_status_relay` (`claude/relay.py`) keep their signatures since `cli.py` calls them directly by name at several call sites (cli.py:266,1083,1152,1377,1387) — update only the import line in `cli.py` to the new path, no wrapper needed.
- `claude_cli.py`, `claude_direct.py`, `claude_interactive.py`, `codex.py`, `copilot.py`, `web.py` (top-level files) are deleted once contents move into the new subpackages.
- `cli.py`, `collector.py`, `provider_discovery.py` — only need their import lines updated to the new module paths; the methods they call (`discover/authenticate/discover_options/fetch/user_identity`) keep the same names/signatures on `Provider`.
- `webview_login.py` — untouched, still the shared cookie-capture implementation called by each provider's `login/web/cookie_capture.py`.
- `tests/test_providers.py`, `tests/test_provider_commands.py`, `tests/test_webview_login.py`, `tests/test_provider_discovery.py`, `tests/test_progress.py` — update import lines to new paths/names directly (no re-export barrel needed to dodge this).

## Implementation steps

1. Add `LoginMethod`, `UsageMethod`, `FallbackUsageMethod` to `providers/base.py`; rework `Provider` into a composition object (`usage_method`, `login_methods`) per the design above.
2. Create `providers/claude/` subpackage: move `claude_cli.py` → `claude/_shared.py`, `claude_direct.py` → `claude/usage/cli/direct.py`, `claude_interactive.py` → `claude/usage/cli/interactive.py`, split `claude/api.py` into `claude/login/web/cookie_capture.py` (auth+discover_options) + `claude/usage/web/private_api.py` (fetch+parsing), split `claude/status.py` into `claude/login/local/settings_file.py` (discover) + `claude/usage/local/relay_file.py` (relay read) + reuse the cli usage modules for the fallback chain; assemble the three Claude `Provider` instances in `claude/provider.py`; keep `claude/relay.py` as-is.
3. Create `providers/codex/` subpackage from `codex.py`: split into `login/local/auth_json.py`, `login/web/cookie_capture.py`, `usage/web/private_api.py`, `usage/cli/app_server.py` (incl. `AppServerClient`), `usage/cli/status_ptv.py`; move the inline temp-`auth.json` credential injection out of `fetch` into the login method's credential-resolution step; assemble in `codex/provider.py`; delete `codex.py`.
4. Create `providers/copilot/` subpackage from `copilot.py` + relevant parts of `web.py`: split into `login/cli/token_reuse.py` (`copilot_cli_credentials`), `login/local/config_file.py` (discover), `usage/web/billing_api.py`, `usage/web/quota_api.py`; decide placement of generic `PrivateWebProvider`/`CopilotEntitlementsProvider` (either `providers/base.py` as a reusable generic usage base, or `copilot/usage/web/entitlements.py`); assemble in `copilot/provider.py`; delete `copilot.py` and `web.py`.
5. Update `registry.py` imports to the new `provider.py` modules, and update import lines directly in `collector.py`, `provider_discovery.py`, and the affected test files.
6. Rewrite `cli.py`'s add/login wizard per the "`provider add` wizard rewrite" section: replace `select_discovered_account`'s single "manual provider adapter" select with the chained service → usage-method → login-method (`credential_kind`-filtered) steps; update `provider_add`, `run_provider_add_wizard`, `provider_login` to call the selected `LoginMethod`'s `discover`/`authenticate`/`discover_options` explicitly instead of going through `Provider`'s old flat delegation; update `print_discovery_choices`/`provider_discover` grouping to service→usage-method.
7. Run `uv run pytest` — full suite must pass; add/extend tests for the new wizard steps (service/usage-method/login-method selection, `required_credential_kind` skip-when-none, single-match auto-select) alongside the existing `test_provider_commands.py` coverage.

## `provider add` wizard rewrite (in scope, not deferred)

Current flow (`cli.py` — explored): `provider_add` (472-622) → `select_discovered_account` (429-469, two chained `select_choice` Textual menus: pick an already-discovered account, or "Manually configure other…" → pick a `service/key` provider adapter by `display_name`) → credential resolution inline in `provider_add` (562-587: from flag, from discovered account, or `provider.authenticate(...)` if `login_url` set) → `provider.discover_options(credential)` → `verify_provider_setup` (276-303: `fetch` + `user_identity`) → `create_account` (155-273, prompts remaining required `ConfigurationField`s via `click.prompt`, persists `AccountConfig` + encrypted credential via `runtime.database.put_credential`). Same shape reused by `run_provider_add_wizard`/`run_first_crawl_wizard`. No prompt library beyond the hand-rolled Textual `select_choice` (`provider_tui.py`) — reuse that, no new dependency needed.

New flow, built on the `UsageMethod`/`LoginMethod` split:

1. **Pick service** — new step, `select_choice("Choose a provider", [SelectionChoice(service, display) for each distinct service in registry])`. (Today this is implicit in the single flat `service/key` list; splitting service from usage-method makes this its own step, matching the user's example of "provider codex → category api → parser web".)
2. **Pick usage method** — `select_choice("Choose how to fetch usage", [...])` listing every registered `UsageMethod`/`Provider` for that service, labeled by `display_name` (e.g. "Codex web API", "Codex app-server", "Codex `/status` CLI") — this is exactly today's `key` dimension, just scoped to the already-picked service and given its own step instead of being buried in one `service/key: display_name` string.
3. **Determine credential need** — read `usage_method.required_credential_kind` off the chosen `Provider`. If `"none"`, skip straight to step 5 (mirrors today's CLI-already-logged-in cases like Claude statusline/Codex `/status`).
4. **Pick login method** — `select_choice("Choose how to sign in", [...])` listing that provider's `login_methods` filtered to `credential_kind == required_credential_kind`, e.g. for Codex web API: "Reuse local `auth.json`" (`discover()`-capable) vs "Sign in via browser" (`authenticate()`). If exactly one match, auto-select and skip the prompt (matches "cli is logged in, no choice needed" case). Run the chosen method's `discover()` (if it already found a usable account/credential, offer it like today's discovered-account list) or `authenticate(options)` (interactive browser/etc.), producing the credential.
5. **Discover options + verify + persist** — unchanged: `provider.discover_options(credential)` (now delegates to whichever `LoginMethod` was used, since option-discovery like Claude's `org_id` lookup is credential-shape-specific), `verify_provider_setup` (`usage_method.fetch` + `user_identity`), prompt remaining `ConfigurationField`s, `create_account`.

Storage/model impact: none required — `AccountConfig.service`/`.provider` still store the usage method's `service`/`key`, `options`/`credential_id` unchanged. The wizard rewrite only touches `cli.py`'s `select_discovered_account`, `provider_add`, `run_provider_add_wizard`, `provider_login` (643-707, same `authenticate`→`fetch`→`user_identity` shape, gets the same step-4 login-method choice when re-authenticating) — replacing the single "manual provider adapter" select with the chained service→usage-method→login-method selects above. `provider_discover`/`print_discovery_choices` (392-413) get a small update to group by service then usage-method instead of one flat `service/key` string, for consistent display.

This wizard rewrite is *why* the `credential_kind`/`required_credential_kind` metadata exists on `LoginMethod`/`UsageMethod` in the base-class design above — it's not speculative, it's consumed immediately by step 3/4. It also directly reduces legacy adapter code: no more per-provider subclass hand-wiring which login path to try in what order inline in `fetch`/`authenticate` (e.g. Copilot's `copilot_cli_credentials()` call buried in `fetch`, Codex app-server's inline temp-file credential injection) — that logic becomes one reusable `LoginMethod` per source, selected explicitly instead of guessed.

## Verification

- `uv run pytest tests/test_providers.py tests/test_provider_commands.py tests/test_provider_discovery.py tests/test_webview_login.py tests/test_progress.py -q` — all green, no behavior changes.
- `grep -rn "from ai_usage.providers" src/ tests/` afterward to confirm no dangling references to deleted top-level modules (`codex.py`, `copilot.py`, `claude_cli.py`, `claude_direct.py`, `claude_interactive.py`).
- Manually skim `registry.py`'s `built_in_registry()` output (or a quick `python -c` import) to confirm all 9 providers still register under the same `(service, key)` pairs.
- Manually run `ai-usage provider add` (or the underlying `run_provider_add_wizard`) for at least one no-credential provider (Codex `/status`) and one credential-needing provider with two login options (Codex web API: local `auth.json` vs browser) to confirm the new chained service→usage-method→login-method prompts behave as designed, then run `uv run pytest tests/test_provider_commands.py -q`.

## Todos

- [x] base.py: LoginMethod/UsageMethod/FallbackUsageMethod
- [x] Split claude subpackage into login/usage
- [x] Split codex.py into login/usage subpackage
- [x] Split copilot.py + web.py into login/usage subpackage
- [ ] Update registry.py wiring
- [ ] Rewrite cli.py provider add/login wizard
- [ ] Update tests + run full suite
