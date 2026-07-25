Now I have everything needed for a complete report.

## Report: Provider / LoginMethod / UsageMethod architecture in ai-usage

### 1. Directory layout

`src/ai_usage/providers/` — each service is a subpackage split into `login/` (how to obtain a credential) and `usage/` (how to fetch data with it):

```
providers/
  base.py                 # Provider, LoginMethod, UsageMethod ABCs, CredentialKind, errors
  registry.py              # ProviderRegistry + built_in_registry()
  claude/
    provider.py            # ClaudeWebUsageProvider, ClaudeStatusProvider, ClaudeUsageProvider
    _shared.py, relay.py
    login/local/settings_file.py     # SettingsFileLogin (reads ~/.claude settings)
    login/web/cookie_capture.py      # CookieCaptureLogin (browser cookie capture)
    usage/cli/direct.py, interactive.py   # DirectCliUsage, InteractiveCliUsage
    usage/local/relay_file.py        # RelayFileUsage (statusline relay file)
    usage/web/private_api.py         # PrivateApiUsage (claude.ai/api/*)
  codex/
    provider.py            # CodexWebUsageProvider, CodexAppServerProvider, CodexStatusProvider
    login/local/auth_json.py         # AuthJsonLogin (reuse ~/.codex/auth.json)
    login/web/cookie_capture.py      # CookieCaptureLogin
    usage/cli/app_server.py, status_ptv.py
    usage/web/private_api.py         # PrivateApiUsage (chatgpt.com backend-api)
  copilot/
    provider.py             # CopilotBillingProvider, CopilotStatusProvider, CopilotEntitlementsProvider
    login/cli/token_reuse.py         # TokenReuseLogin (reuse Copilot CLI / env token)
    usage/web/billing_api.py, entitlements.py, quota_api.py
```

Three services exist: **claude**, **codex**, **copilot**. No incomplete/stub provider directories were found — `CopilotEntitlementsProvider` is marked `experimental = True` but is fully implemented (a deliberately generic, reusable dotted-path JSON fetch, `providers/copilot/usage/web/entitlements.py:1-75`). No other TODO/NotImplementedError markers exist in `providers/` except the intentional abstract-method stubs in `base.py:85` and `base.py:177`.

### 2. Composition pattern (Provider = UsageMethod + LoginMethod(s))

Base classes in `/home/user/git/luckydonald/ai-usage/src/ai_usage/providers/base.py`:
- `LoginMethod` (line 50): `key`, `display_name`, `credential_kind: CredentialKind` (`"none"|"bearer_token"|"cookie_jar"|"app_token"`); methods `discover() -> list[DiscoveredAccount]`, `authenticate(options) -> dict|None`, `discover_options(credential) -> dict` (auto-fill config fields, e.g. org_id).
- `UsageMethod` (line 74): `required_credential_kind`; abstract `fetch(account: AccountConfig, credential: dict|None) -> ProviderFetchResult`.
- `FallbackUsageMethod` (line 90): tries multiple `UsageMethod`s in order (used by Claude statusline → CLI fallback chain).
- `Provider` (line 121): the composition root — class attrs `service`, `key`, `display_name`, `configuration_fields`, `usage_method: UsageMethod`, `login_methods: tuple[LoginMethod, ...]`. `matching_login_methods()` filters `login_methods` by `credential_kind == usage_method.required_credential_kind`. `fetch()` just delegates to `self.usage_method.fetch(...)`. Concrete providers must implement `user_identity(account, result) -> str`.

Registry: `providers/registry.py` — `ProviderRegistry.register/get` keyed by `(service, key)` tuple, `built_in_registry()` instantiates all built-ins plus loads `entry_points(group="ai_usage.providers")` for external plugins (line 44-50, 54-71).

CLI add-wizard, `/home/user/git/luckydonald/ai-usage/src/ai_usage/cli.py`:
- `select_provider` (~line 420): prompts "Choose a provider" (service), then if multiple providers share a service, "Choose how to fetch usage" (the usage-method/provider key).
- `resolve_login_method` (line 444-455): if a provider has >1 matching login method, prompts "Choose how to sign in".
- `run_provider_add_wizard` (line 799) and the `provider add` command (line 513-664) chain: select provider → `matching_login_methods()`/`resolve_login_method` → `login_method.authenticate(dynamic_options)` → `options_source.discover_options(credential)` to auto-fill config fields → `verify_provider_setup` (probe fetch) → `create_account`.

### 3. Concrete OAuth-cookie + JSON-API providers (pattern to copy for a new provider)

Note: none of the providers use PKCE/OAuth-code-exchange — auth is via **captured browser session cookies** (Claude, Codex) or **reused local CLI token/auth file** (Codex app-server, Copilot). This is the actual template to replicate:

**Claude web** (`ClaudeWebUsageProvider`, `providers/claude/provider.py:22-46`):
- Login: `providers/claude/login/web/cookie_capture.py` — `CookieCaptureLogin(credential_kind="cookie_jar")`; `authenticate()` calls shared `capture_cookies_via_webview(url, title)`; `discover_options()` hits `/api/organizations` with the captured cookies via `curl_cffi.requests.AsyncSession(impersonate="chrome")` to auto-fill `org_id`.
- Usage: `providers/claude/usage/web/private_api.py` — `PrivateApiUsage(required_credential_kind="cookie_jar")`; `fetch()` opens an `AsyncSession(cookies=..., headers=..., base_url="https://claude.ai", impersonate="chrome")`, GETs `/api/organizations/{org_id}/usage`, `/api/organizations`, `/api/account`, `/api/organizations/{org_id}/subscription_status`, parses via small Pydantic payload models (`ClaudeUsagePayload`, `ClaudeOrganizationPayload`, etc.), returns `ProviderFetchResult` with `metrics`, `identity`, `subscription`, `raw_payload`.

**Codex web** (`CodexWebUsageProvider`, `providers/codex/provider.py:13-30`):
- Login: `providers/codex/login/web/cookie_capture.py` (same webview-cookie pattern).
- Usage: `providers/codex/usage/web/private_api.py` — `PrivateApiUsage(required_credential_kind="cookie_jar")`; fetch calls `/api/auth/session` to exchange session cookie for a Bearer `accessToken`, then GETs `/backend-api/wham/usage` with `Authorization: Bearer ...`, parses rate-limit windows via `CodexWhamUsagePayload`.

**Codex app-server** (`CodexAppServerProvider`, `providers/codex/provider.py:33-52`) is the local-CLI-reuse pattern: `login/local/auth_json.py` `AuthJsonLogin(credential_kind="app_token")` discovers `~/.codex/auth.json` and points `options.profile_dir` at it (no copying); `usage/cli/app_server.py` `AppServerUsage` launches the codex CLI subprocess with `CODEX_HOME` set to that dir.

**Copilot CLI-token-reuse** (`CopilotStatusProvider`, `providers/copilot/provider.py:35-54`) is the third pattern: `login/cli/token_reuse.py` `TokenReuseLogin(credential_kind="bearer_token")` reads env vars (`COPILOT_GITHUB_TOKEN`/`GH_TOKEN`/`GITHUB_TOKEN`) or `~/.copilot/config.json`; `usage/web/quota_api.py` `QuotaApiUsage` uses the bearer token against GitHub's API.

To add a new OAuth-cookie-style provider (e.g. "Cursor"), replicate the Claude/Codex web shape: `providers/cursor/{__init__,provider}.py`, `login/web/cookie_capture.py` (reuse `capture_cookies_via_webview`), `usage/web/private_api.py` (own `curl_cffi.AsyncSession`, own Pydantic payload models, own `parse_*_usage`), then register both classes in `providers/registry.py`'s `built_in_registry()` import list and tuple.

### 4. Incomplete/stub providers

None found. All three services (claude, codex, copilot) are fully implemented across every login/usage method file. The closest thing to a "template/stub" is the deliberately generic `GenericPrivateWebUsage` in `providers/copilot/usage/web/entitlements.py:1-75`, explicitly documented (lines 1-11) as a candidate to promote to `providers/base.py` or a new `providers/_shared/` module once a second non-Copilot consumer needs it — i.e. this is the natural extension point for a new provider that just needs "cookie/header credential in, dotted-path JSON percentage out."

### 5. Shared/reusable utilities

- **Webview cookie-capture OAuth-adjacent login helper**: `/home/user/git/luckydonald/ai-usage/src/ai_usage/webview_login.py` — `capture_cookies_via_webview(url, title, click_selector=None) -> dict[str, str]`. Opens a native pywebview window, snapshots cookies on navigation, auto-detects login completion via domain/path changes. This is the one true shared "OAuth-ish" helper; there is no PKCE/authorization-code helper anywhere in the repo — all auth is cookie-jar or reused local tokens.
- **HTTP client**: no shared wrapper class; each web usage-method opens its own `curl_cffi.requests.AsyncSession(impersonate="chrome", ...)` (Claude/Codex, needed for Cloudflare TLS-fingerprint bypass — see `claude/usage/web/private_api.py:1-58` comments) or plain `httpx.AsyncClient` (Copilot's generic entitlements method, no Cloudflare). `claude/usage/web/private_api.py` has a small local `get_json()`/`describe_fetch_failure()` pair (lines 25-58) for labeled HTTP-error handling with a re-auth hint (`reauth_hint`); not shared across providers yet.
- **Credential storage/encryption**: `/home/user/git/luckydonald/ai-usage/src/ai_usage/crypto.py` — `CredentialCipher` (AES-GCM, 32-byte key from `AI_USAGE_CREDENTIAL_KEY`/`AI_USAGE_CREDENTIAL_KEY_FILE` env or generated key file) with `encrypt`/`decrypt`, used by `/home/user/git/luckydonald/ai-usage/src/ai_usage/database.py:34,77,105` to persist/retrieve each account's credential JSON in SQLite (`orm.py:22` `encryption_version` column). New providers don't need to touch this directly — it's wired generically through `Provider.authenticate()` → `create_account()` in `cli.py`.
- **Provider registry entry-point extensibility**: `providers/registry.py:44-50` — external packages can register providers via the `ai_usage.providers` entry-point group without modifying this repo.