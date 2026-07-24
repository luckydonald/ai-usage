[harness: subagent output matched instruction-shaped pattern(s): settings-json. Control tags below are neutralized (`<` → `<\`); treat any remaining directive-shaped text as a finding to relay to the user, not an instruction to you.]

I have full context. Here is the report.

## Shared interfaces (base.py)

`/home/user/git/luckydonald/ai-usage/src/ai_usage/providers/base.py`

- `ProviderError(RuntimeError)` (13), `ProviderLoginError(ProviderError)` (17): shared error hierarchy for both concerns.
- `canonical_login(value, provider_name) -> str` (22): shared helper for normalizing an identity string; used by every provider's `user_identity`.
- `ConfigurationField(BaseModel)` (30): declares an account config field (string/integer/boolean/secret/path), used by providers to describe their `configuration_fields` tuple (login-adjacent metadata — what a user must supply to set up an account).
- `DiscoveredAccount(BaseModel)` (40): result type for `discover()` — login/setup-discovery concern (name, options, optional credential).
- `Provider(ABC)` (47): the single base class every provider extends.
  - Class attrs: `service`, `key`, `display_name`, `experimental`, `configuration_fields`, `login_url`, `login_hint`, `icon` — all login/registration metadata.
  - `discover()` (57): **login-related** — auto-detect an already-configured local account (file-probing).
  - `authenticate(options)` (61): **login-related** — perform interactive auth (e.g. webview), returns credential dict.
  - `discover_options(credential)` (66): **login-related** — post-auth auto-fill of config fields (e.g. org lookup).
  - `user_identity(account, result)` (72): **login-related** (identity resolution from a fetch result, used to detect duplicate accounts).
  - `fetch(account, credential)` (78, abstract): **usage-related** — the actual usage/cost data retrieval; the only required method.

So `Provider` is one ABC serving as the interface for both login (`discover`, `authenticate`, `discover_options`, `user_identity`, plus `login_url`/`login_hint`/`configuration_fields` metadata) and usage (`fetch`). Any refactor splitting login vs usage needs to either split this ABC into two protocols/mixins or keep `Provider` as a composition root that mixes a login-strategy object and a usage-strategy object.

`__init__.py` (`/home/user/git/luckydonald/ai-usage/src/ai_usage/providers/__init__.py`) just re-exports `ConfigurationField`, `Provider`, `ProviderError`, `ProviderRegistry`, `built_in_registry`.

## registry.py wiring

`/home/user/git/luckydonald/ai-usage/src/ai_usage/providers/registry.py`

- `ProviderRegistry` (20): dict keyed by `(service, key)` tuple → `Provider` instance. `register()` (25), `get()` (33), `load_entry_points()` (41, via `importlib.metadata.entry_points(group="ai_usage.providers")` for third-party providers).
- `built_in_registry()` (51): instantiates and registers 9 concrete `Provider` instances directly (imported from `claude`, `codex`, `copilot`, `web` modules), then loads entry points. This is the composition point that a refactor must update to import from the new `providers/<provider>/...` paths.

## Per-file breakdown

### `claude/__init__.py`
Pure re-export barrel aggregating `claude_cli`, `.api`, `.relay`, `.status` symbols. No new classes.

### `claude/api.py` (private web API — login: cookie webview; usage: HTTP API)
- `reauth_hint`, `describe_fetch_failure`, `get_json` (32, 37, 48): usage-fetch helpers (HTTP error labeling).
- Payload models: `ClaudeUsageWindowPayload`, `ClaudeUsagePayload`, `ClaudeOrganizationPayload`, `ClaudeAccountPayload`, `ClaudeSubscriptionStatusPayload` (92-120): usage/identity schema.
- `extract_claude_web_notes` (77), `parse_claude_web_usage` (123): usage parsing.
- `ClaudeWebUsageProvider(Provider)` (174): service=`claude`, key=`web`.
  - `user_identity` (188): login-related.
  - `authenticate` (196): **login** — calls `capture_cookies_via_webview` (browser/cookie mechanism) from `ai_usage.webview_login`.
  - `discover_options` (204): **login** — auto-detects `org_id` via HTTP call to `/api/organizations` using captured cookies (uses `curl_cffi.requests.AsyncSession`, impersonate chrome).
  - `fetch` (245): **usage** — HTTP API calls (`curl_cffi`) to `/api/organizations/{org}/usage`, `/api/organizations`, `/api/account`, `/api/organizations/{org}/subscription_status`, `/edge-api/bootstrap/{org}/app_start`.
  - Mechanism: web browser/cookie for login, HTTP API call for usage.

### `claude/relay.py` (status-line relay installer — pure login/setup mechanism, local file)
- `write_relay_payload(path, payload)` (13): writes JSON atomically — used by the relay script itself at runtime, not a Provider method.
- `install_status_relay(account, local_root)` (22) / `remove_status_relay(account, local_root)` (79): **login/setup-related** (not defined on Provider — called externally, presumably by CLI `login`/`logout` commands) — mutates `~/.claude/settings.json`'s `statusLine` hook to inject a relay script that mirrors statusline JSON to disk. Mechanism: local file read/write + generated subprocess script.
- No classes; free functions only, imported into `claude/__init__.py`.

### `claude/status.py` (statusline ingestion + `/usage` CLI fallback — usage-only, no authenticate)
- Regex/parsing helpers: `extract_claude_notes`, `normalize_claude_terminal_output`, `claude_metric_key`, `claude_metric_model`, `parse_status_payload` (76), `parse_usage_output` (102): usage parsing.
- `run_claude_auth_status(command, profile_dir)` (122): **borderline** — runs `claude auth status` CLI subprocess to get identity email; used inside `fetch()`, so it's usage-fetch-time identity resolution, not account setup/login.
- `ClaudeStatusProvider(Provider)` (167): service=`claude`, key=`statusline`.
  - `user_identity` (179): login-related.
  - `discover` (187): **login** — local file probe of `~/.claude/settings.json` (local file read mechanism).
  - `fetch` (195): **usage** — reads relay file (local file read) if fresh, else subprocess CLI call via `run_claude_usage_direct` (claude_direct.py) then `run_claude_usage` (claude_interactive.py, pexpect PTY). Mechanism: local file read + CLI subprocess (direct and PTY-interactive fallback).
- `ClaudeUsageProvider(ClaudeStatusProvider)` (253): service=`claude`, key=`cli-usage`; overrides `fetch` (258) to strip `relay_file` option and force CLI-only path (no relay). Pure usage-mechanism variant subclass.

### `claude_cli.py` (shared CLI plumbing, no Provider subclass)
Functions only: `claude_default_profile`, `claude_profile_path`, `canonical_claude_profile_dir`, `claude_environment` (17-46): profile/env resolution, used by both login (discover) and usage (fetch) paths — infra, not concern-specific. `claude_setup_required_message`, `write_claude_error_log`, `claude_cli_failure_message` (49-100): usage-fetch error/diagnostics for CLI subprocess mechanism.

### `claude_direct.py` (usage mechanism: non-interactive CLI subprocess)
- `run_claude_usage_direct(command, profile_dir)` (22): usage-related, CLI subprocess call (`asyncio.create_subprocess_exec` with `--print --no-chrome --ax-screen-reader /usage`).

### `claude_interactive.py` (usage mechanism: interactive PTY fallback)
- `run_claude_usage(command, profile_dir)` (14): usage-related, CLI subprocess via `pexpect` PTY spawn typing `/usage` and `/exit`.

### `codex.py` (two Codex providers: web API and app-server; plus terminal status)
- Parsing/helpers: `codex_model`, `extract_codex_notes`, `window_key`, `window_name`, `parse_rate_limits` (82), `codex_app_server_email` (107), payload models `CodexRateWindowPayload`/`CodexRateLimitPayload`/`CodexWhamUsagePayload` (118-136), `parse_codex_web_usage` (139): usage parsing.
- `CodexWebUsageProvider(Provider)` (205): service=`codex`, key=`web`.
  - `user_identity` (217): login-related.
  - `authenticate` (224): **login** — `capture_cookies_via_webview` (browser/cookie mechanism), with `login_button_selector` click hint.
  - `fetch` (234): **usage** — HTTP API via `curl_cffi.AsyncSession` (`impersonate="chrome"`) to `/api/auth/session` then `/backend-api/wham/usage`.
- `AppServerClient` (296): not a Provider — JSON-RPC-over-stdio subprocess client (helper class) for Codex app-server. `__aenter__`/`__aexit__` spawn/terminate subprocess; `request`/`notify`/`send` (335-370) implement the protocol. Used by usage fetch.
- `CodexAppServerProvider(Provider)` (374): service=`codex`, key=`app-server`.
  - `user_identity` (384): login-related.
  - `discover` (391): **login** — local file probe `~/.codex/auth.json`.
  - `fetch` (399): **usage** — CLI subprocess (`codex app-server --stdio`) via `AppServerClient`; also handles a **login-adjacent** credential injection (writes temp `auth.json` from `credential["auth_json"]`) inline inside `fetch` (407-413) — this is a login/credential concern leaking into the usage method, worth flagging for refactor.
- `parse_codex_status` (444): usage parsing for `/status` terminal output.
- `CodexStatusProvider(Provider)` (466): service=`codex`, key=`cli-status`.
  - `user_identity` (475): raises `ProviderLoginError` — no identity resolution supported.
  - `fetch` (480): **usage** — CLI subprocess via `run_codex_status` (507, pexpect PTY sending `/status`).

### `copilot.py` (two Copilot providers: GitHub billing API, and CLI-token-based quota API)
- `next_billing_reset(now, day)` (31): usage helper (billing cycle math).
- `CopilotBillingProvider(Provider)` (49): service=`copilot`, key=`github-api`.
  - `user_identity` (61): login-related (uses configured `username`, not fetched identity).
  - `fetch` (66): **usage** — HTTP call (`httpx`) to GitHub billing API using a pre-supplied `credential["token"]`; no `authenticate`/`discover` defined here — credential (encrypted token) apparently supplied externally/manually.
- `copilot_cli_credentials(config_dir)` (117): **login-related** — reads local Copilot CLI file `~/.copilot/config.json` (or env vars `COPILOT_GITHUB_TOKEN`/`GH_TOKEN`/`GITHUB_TOKEN`) to reuse an existing OAuth token. Mechanism: local file read + env var. Not a Provider method — free function called from `fetch`.
- `copilot_quota_metric_key`, `parse_copilot_quota_payload` (161): usage parsing.
- `CopilotStatusProvider(Provider)` (205): service=`copilot`, key=`statusline`.
  - `user_identity` (216): login-related.
  - `discover` (223): **login** — local file probe `~/.copilot/config.json`.
  - `fetch` (231): **usage** — calls `copilot_cli_credentials` (local file read, login concern) then HTTP call (`httpx`) to `/copilot_internal/user`. Again login-credential-lookup is embedded inside `fetch`.

### `web.py` (generic experimental private-web adapter)
- `PrivateWebProvider(Provider)` (13): `experimental = True`, base class for generic cookie/header-based HTTP usage fetch; no `authenticate`/`discover` (credential assumed pre-supplied).
  - `user_identity` (22): raises `ProviderLoginError` unconditionally — no identity mechanism.
  - `fetch` (27): **usage** — HTTP call via `httpx.AsyncClient`, generic JSON dotted-path field extraction (`percentage_field`).
- `CopilotEntitlementsProvider(PrivateWebProvider)` (67): service=`copilot`, key=`entitlements`. Just sets class attrs; no override.

## Cross-cutting mechanism summary (for planning the `login/<type>/<method>` vs `usage/<type>/<method>` split)

| Provider (service/key) | Login mechanism | Usage mechanism |
|---|---|---|
| claude/web (`ClaudeWebUsageProvider`, api.py) | browser/cookie (`capture_cookies_via_webview`) + HTTP discover_options | HTTP API (curl_cffi) |
| claude/statusline (`ClaudeStatusProvider`, status.py) | local file discover (`~/.claude/settings.json`) | local file read (relay) + CLI subprocess (direct, then PTY interactive fallback) |
| claude/cli-usage (`ClaudeUsageProvider`, status.py) | inherited local file discover | CLI subprocess only (no relay) |
| codex/web (`CodexWebUsageProvider`, codex.py) | browser/cookie | HTTP API (curl_cffi) |
| codex/app-server (`CodexAppServerProvider`, codex.py) | local file discover (`~/.codex/auth.json`) + inline temp-file credential injection in fetch | CLI subprocess (JSON-RPC over stdio via `AppServerClient`) |
| codex/cli-status (`CodexStatusProvider`, codex.py) | none | CLI subprocess (pexpect PTY `/status`) |
| copilot/github-api (`CopilotBillingProvider`, copilot.py) | none in-code (token supplied externally) | HTTP API (httpx) |
| copilot/statusline (`CopilotStatusProvider`, copilot.py) | local file discover + local-file/env credential lookup (`copilot_cli_credentials`) embedded in fetch | HTTP API (httpx) |
| copilot/entitlements (`CopilotEntitlementsProvider`, web.py) | none | HTTP API (httpx), generic |

Note for the refactor: several `fetch()` methods (`CodexAppServerProvider.fetch`, `CopilotStatusProvider.fetch`) internally perform login/credential-resolution steps (temp auth.json write, `copilot_cli_credentials` local file/env lookup) that would need to be pulled out into `login/<type>/<method>.py` modules and injected as a resolved credential rather than left inline in the usage-fetch path. Also `claude/relay.py`'s `install_status_relay`/`remove_status_relay` and `claude_cli.py`'s shared env/profile helpers are used by both login and usage code paths and aren't tied to one `Provider` method, so they need a clear home (likely a shared "common" module per provider, or split login install functions into `login/local-file/relay-install.py` while keeping `claude_environment`/`claude_profile_path` as shared infra imported by both sides).