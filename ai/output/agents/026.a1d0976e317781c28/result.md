[harness: subagent output matched instruction-shaped pattern(s): settings-json. Control tags below are neutralized (`<` → `<\`); treat any remaining directive-shaped text as a finding to relay to the user, not an instruction to you.]

I now have a complete picture. Here's the research report.

## 1. Where the warning is emitted

`/home/user/git/luckydonald/ai-usage/src/ai_usage/providers/claude.py:348-358`, inside `ClaudeWebUsageProvider.fetch` (class starts at line 230):

```python
subscription_info: ClaudeSubscriptionStatusPayload | None = None
try:
    status_response = await client.get(
        f"/api/organizations/{org_id}/subscription_status"
    )
    status_response.raise_for_status()
    status_payload = status_response.json()
    raw_payload["subscription_status"] = status_payload
    subscription_info = ClaudeSubscriptionStatusPayload.model_validate(status_payload)
except Exception as exception:  # noqa: BLE001
    LOGGER.warning("could not fetch Claude subscription status: %s", exception)   # line 358
# end try
```

This is a best-effort sub-fetch inside the main `fetch()` (called from `Collector.fetch_account`, `/home/user/git/luckydonald/ai-usage/src/ai_usage/collector.py:94`). A 403 here (Cloudflare block or session/cookie expiry) is swallowed — it does not raise `ProviderError` and does not fail the overall fetch (unlike the required usage call at line 310-312 which does raise on non-200). Same pattern repeats for organization info (line 333-335), account info (line 344-345), and app_start bootstrap (line 375-376).

## 2. How Claude auth/cookies are obtained/stored

- **Capture**: `ClaudeWebUsageProvider.authenticate()` at `claude.py:244-250` opens a native webview via `capture_cookies_via_webview()` (`/home/user/git/luckydonald/ai-usage/src/ai_usage/webview_login.py:93-218`), which snapshots cookies on page load while still on `login_url`'s domain and detects "logged in" via navigation away from `/login`. `login_url = "https://claude.ai/login"` (`claude.py:242`).
- **Shape**: credential dict is `{"cookies": {...}}` (optionally `headers`), consumed in `fetch()` at `claude.py:302-303` (`cookies = (credential or {}).get("cookies", {})`, `headers = (credential or {}).get("headers", {})`).
- **Transport**: requests use `curl_cffi.requests.AsyncSession` with `impersonate="chrome"` (`claude.py:261-263`, `306-309`) specifically because claude.ai sits behind Cloudflare and ties `cf_clearance` to the TLS fingerprint — a plain client (or an expired/invalid cookie jar) gets 403'd.
- **Org auto-detect**: `discover_options()` at `claude.py:252-291` hits `/api/organizations` to fill in `org_id`; warns (doesn't raise) on failure.
- **Storage**: credentials are encrypted at rest via `Database.put_credential`/`get_credential` (`/home/user/git/luckydonald/ai-usage/src/ai_usage/database.py:74-116`), using `CredentialCipher` (`ai_usage/crypto.py`) keyed by `paths.credential_key`. `AccountConfig.credential_id` (config YAML, `/home/user/git/luckydonald/ai-usage/src/ai_usage/config.py:89-99`, `109-129`) references the DB row. On fetch, `Collector.fetch_account` decrypts it (`collector.py:88-90`: `credential = await self.database.get_credential(account.credential_id)`).
- No token refresh logic exists for the web provider — cookies are static until re-captured; there's no cookie-jar persistence beyond the encrypted DB blob and no auto-refresh on expiry/403.

## 3. Existing re-auth / login flow patterns to mirror

- **`ai_usage/cli.py:554-604`** — `provider_app.command("login")` (`provider_login`): explicit CLI command `ai-usage provider login --account <id>` that:
  1. Loads the account, calls `provider.authenticate(account.options)` (line 570) — wrapped in try/except `ProviderError` → `click.ClickException` (571-573).
  2. Verifies with a probe `provider.fetch(account, credential)` (line 581) and checks `probe_result.status == FetchStatus.ERROR` (588).
  3. On success, re-encrypts via `runtime.database.put_credential(...)` (595-597) and updates `account.credential_id` via `runtime.config.save_account(...)` (598).
- **`ai_usage/cli.py:460-518`** — the initial account-creation flow (`provider_add`/similar) has an analogous inline pattern: falls back to `provider.authenticate(dynamic_options)` when no credential/secret was supplied and `provider.login_url` exists and terminal is interactive (466-481), then does the same fetch-probe verification (488-507) before persisting.
- **Codex mirrors the exact same shape** in `/home/user/git/luckydonald/ai-usage/src/ai_usage/providers/codex.py:199-207` (`CodexWebUsageProvider.authenticate`), including `login_url`, `login_hint`, and a `login_button_selector` used for auto-click since chatgpt.com's CSP blocks `evaluate_js`.
- Both web providers (`claude.py`, `codex.py`) declare `login_url` / optional `login_hint` class attributes (base contract in `/home/user/git/luckydonald/ai-usage/src/ai_usage/providers/base.py:40-41`) that the CLI login flow keys off of — this is the extension point to hook a "re-auth on 403" trigger into, since today nothing automatically detects an expired-cookie 403 and prompts re-login; it's a fully manual, user-invoked `provider login` command.

## 4. Structure of `claude.py`

File: `/home/user/git/luckydonald/ai-usage/src/ai_usage/providers/claude.py`

- Lines 38-44: regexes for statusline/`/usage` CLI output parsing (`ANSI_PATTERN`, `SECTION_PATTERN`, `PROMO_PATTERN`).
- `extract_claude_notes` (47-50), `extract_claude_web_notes` (62-74) — promo banner text extraction (CLI vs web).
- `claude_metric_key` (77-86), `claude_metric_model` (89-99) — metric key/model derivation from section titles.
- `parse_status_payload` (102-125) — parses statusline relay JSON.
- `parse_usage_output` (128-145) — parses `/usage` terminal output text.
- Pydantic payload models (148-176): `ClaudeUsageWindowPayload`, `ClaudeUsagePayload`, `ClaudeOrganizationPayload`, `ClaudeAccountPayload`, `ClaudeSubscriptionStatusPayload`.
- `parse_claude_web_usage` (179-227) — validates/falls back on raw dict for `/api/organizations/{id}/usage`.
- **`ClaudeWebUsageProvider`** (230-407): `service="claude"`, `key="web"`, `login_url`; `authenticate` (244-250), `discover_options` (252-291), `fetch` (293-406) — orchestrates usage (required), organizations, account, subscription_status, app_start bootstrap calls; builds `identity`/`subscription`/`raw_payload`.
- **`ClaudeStatusProvider`** (410-478): `key="statusline"`; `discover` (422-428) finds `~/.claude/settings.json`; `fetch` (430-477) reads a relay file (fast path) or falls back to `run_claude_usage` (spawns `claude` via pexpect).
- **`ClaudeUsageProvider(ClaudeStatusProvider)`** (481-496): `key="cli-usage"`, forces the direct (non-relay) path.
- `run_claude_usage` (499-527) — pexpect-driven `/usage` session.
- `write_relay_payload` (530-536), `install_status_relay` (539-591), `remove_status_relay` (594-626) — manage the statusline relay script/settings.json hook used by `ClaudeStatusProvider`.