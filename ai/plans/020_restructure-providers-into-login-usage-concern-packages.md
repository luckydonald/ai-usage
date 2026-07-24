# Restructure `providers/` into login/usage concern packages

## Context

`src/ai_usage/providers/` currently mixes two independent concerns inside one `Provider` class per file: **login** (how a credential/token is acquired — local file, browser+cookie capture, CLI token reuse) and **usage** (how the actual metrics API/CLI is called once a credential exists). Several providers already have multiple alternative login paths for the same usage call (e.g. Codex app-server: local `auth.json` file *or* browser cookie capture could both yield a usable credential) and multiple fallback usage mechanisms for the same login (e.g. Claude statusline: relay-file read → direct CLI → PTY-interactive CLI). Today these are tangled together inside single `fetch()`/`discover()` methods per provider file (`codex.py`, `copilot.py`, `claude/status.py`, `claude/api.py`), making it hard to see or reuse a login mechanism across providers, or reason about a usage mechanism independent of how the credential was obtained.

Goal: split login and usage into standalone, composable objects, organized as `providers/<provider>/login/<type>/<method>.py` and `providers/<provider>/usage/<type>/<method>.py`, with a thin per-provider `Provider` that just wires: which login method(s) can discover/produce a credential, and which usage method(s) actually call the API/CLI with that credential. Pure refactor — no behavior change, all existing tests must pass (with import paths updated).

## Design

### New base abstractions (`providers/base.py`)

Keep `Provider(ABC)`, `ProviderError`, `ProviderLoginError`, `ConfigurationField`, `DiscoveredAccount`, `canonical_login` as-is (public API used by `cli.py`, `collector.py`, `provider_discovery.py`, tests must not change).

Add two new small ABCs alongside:

- `LoginMethod(ABC)` — one way to obtain/discover a credential.
  - `discover() -> DiscoveredAccount | None` (optional, default returns `None`)
  - `authenticate(options) -> dict` (optional, default raises `ProviderLoginError`)
  - `discover_options(credential) -> dict` (optional, default returns `{}`)
- `UsageMethod(ABC)` — one way to fetch usage given a credential.
  - `fetch(account, credential) -> FetchResult` (abstract)

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

### Back-compat surface

- `providers/__init__.py` keeps exporting `ConfigurationField`, `Provider`, `ProviderError`, `ProviderRegistry`, `built_in_registry` — unchanged.
- `providers/claude/__init__.py`, `providers/codex/__init__.py` (new), `providers/copilot/__init__.py` (new) re-export the same class/function names tests currently import (per Explore agent's list: `ClaudeStatusProvider`, `ClaudeWebUsageProvider`, `install_status_relay`, `remove_status_relay`, `CodexStatusProvider`, `CodexWebUsageProvider`, `CopilotBillingProvider`, `CopilotStatusProvider`, `copilot_cli_credentials`, parsing helper functions, etc.) so `tests/test_providers.py` imports keep working unchanged where possible.
- `registry.py`'s `built_in_registry()` only needs its internal imports updated to `from .claude.provider import ...` etc.; its public behavior is unchanged.
- `claude_cli.py`, `claude_direct.py`, `claude_interactive.py`, `codex.py`, `copilot.py`, `web.py` (top-level files) are removed once contents move into the new subpackages — any remaining external import of these exact paths (none found outside providers/tests per Explore agent) is not a concern; test files import via `ai_usage.providers.claude`/`.codex`/`.copilot` package names already, which continue to resolve.

### Files NOT touched

- `cli.py`, `collector.py`, `provider_discovery.py` — they only call `Provider.discover/authenticate/discover_options/fetch/user_identity` and `install_status_relay/remove_status_relay`, all of which keep their exact signatures and import paths (`from ai_usage.providers.claude import install_status_relay, remove_status_relay`).
- `webview_login.py` — untouched, still the shared cookie-capture implementation called by `login/web/cookie_capture.py` in each provider.

## Implementation steps

1. Add `LoginMethod`, `UsageMethod`, `FallbackUsageMethod` to `providers/base.py`; update `Provider` to delegate `discover/authenticate/discover_options/fetch` to assigned method objects (constructor takes `login_method`/`login_methods` and `usage_method`/`usage_methods`).
2. Create `providers/claude/` subpackage: move `claude_cli.py` → `claude/_shared.py`, `claude_direct.py` → `claude/usage/cli/direct.py`, `claude_interactive.py` → `claude/usage/cli/interactive.py`, split `claude/api.py` into `claude/login/web/cookie_capture.py` (auth+discover_options) + `claude/usage/web/private_api.py` (fetch+parsing), split `claude/status.py` into `claude/login/local/settings_file.py` (discover) + `claude/usage/local/relay_file.py` (relay read) + reuse the cli usage modules for the fallback chain; assemble `ClaudeWebUsageProvider`/`ClaudeStatusProvider`/`ClaudeUsageProvider` in `claude/provider.py`; update `claude/__init__.py` re-exports; keep `claude/relay.py` as-is.
3. Create `providers/codex/` subpackage from `codex.py`: split into `login/local/auth_json.py`, `login/web/cookie_capture.py`, `usage/web/private_api.py`, `usage/cli/app_server.py` (incl. `AppServerClient`), `usage/cli/status_ptv.py`; move the inline temp-`auth.json` credential injection out of `fetch` into the login method's credential-resolution step; assemble in `codex/provider.py`; delete `codex.py`.
4. Create `providers/copilot/` subpackage from `copilot.py` + relevant parts of `web.py`: split into `login/cli/token_reuse.py` (`copilot_cli_credentials`), `login/local/config_file.py` (discover), `usage/web/billing_api.py`, `usage/web/quota_api.py`; decide placement of generic `PrivateWebProvider`/`CopilotEntitlementsProvider` (either `providers/base.py` as a reusable generic usage base, or `copilot/usage/web/entitlements.py`); assemble in `copilot/provider.py`; delete `copilot.py` and `web.py` (or keep `web.py` only if `PrivateWebProvider` is meant to stay a cross-provider generic export).
5. Update `registry.py` imports to the new `provider.py` modules; run full test suite; update only the import lines in `tests/test_providers.py`, `tests/test_provider_commands.py`, `tests/test_webview_login.py`, `tests/test_provider_discovery.py`, `tests/test_progress.py` to point at new module paths where a symbol moved (re-export barrels in each `__init__.py` should minimize how many import lines actually need changes).
6. Run `uv run pytest` (or repo's test command) — full suite must pass unchanged in behavior.

## Verification

- `uv run pytest tests/test_providers.py tests/test_provider_commands.py tests/test_provider_discovery.py tests/test_webview_login.py tests/test_progress.py -q` — all green, no behavior changes.
- `grep -rn "from ai_usage.providers" src/ tests/` afterward to confirm no dangling references to deleted top-level modules (`codex.py`, `copilot.py`, `claude_cli.py`, `claude_direct.py`, `claude_interactive.py`).
- Manually skim `registry.py`'s `built_in_registry()` output (or a quick `python -c` import) to confirm all 9 providers still register under the same `(service, key)` pairs.
