# Plan: ClaudeUsage.app local-API provider for Claude

## Context
The ClaudeUsage macOS app serves the user's Claude subscription usage as JSON on `http://127.0.0.1:47291` (spec: `ai/references/Usage for Claude.app/claude-usage.skill.md`). We add it as another `claude` provider next to `web`, `statusline` and `cli-usage`. It needs no credential and no Cloudflare impersonation, because it is a loopback API.

Decisions:
- Display name: `ClaudeUsage.app (local API)`. Provider key: `app` (not specified, so I picked the short style of the existing keys). Marked `experimental`.
- Identity: the API exposes no email (`source` is only `"email"` or `"claudeCode"`). So the login comes from an optional `email` option. Its default is the email from `claude auth status`, and the user can override it with `--email you@x.com`.

## Changes
1. **Usage method** `src/ai_usage/providers/claude/usage/local/usage_app.py`, class `UsageAppUsage(UsageMethod)` with `required_credential_kind = "none"`.
   - Use `httpx.AsyncClient(base_url=options.get("base_url", default), timeout=...)`.
   - Fetch `/session`, `/weekly` and `/opus`. A 404 `window_unavailable` means that window is skipped, not an error. A 503 `no_data` raises `ProviderError` (retry later). A connection error raises `ProviderError("ClaudeUsage app not running / Local API disabled (Settings → General → Local API)")`.
   - Metrics follow the existing Claude conventions:
     - `five-hours`, "Five hours", `window_seconds=18000`
     - `seven-days`, "Seven days", `window_seconds=604800`
     - `seven-days-opus`, "Current week (Opus)", `model="Opus"`, `window_seconds=604800`
   - Each metric uses `Usage(percentage=percentUsed)`. `reset_at` is taken from `resetsAt` (null is fine). `observed_at` is the response's `lastUpdated`. `metadata` carries `source`.
   - If `lastUpdated` is older than a few minutes, return `FetchStatus.STALE` or add a note. If no window is available, raise `ProviderError`, so we never report a fake 0%.
   - Keep `raw_payload` as the combined responses.
   - Identity on the result: `AccountIdentity(email=...)` from the option, or from the `claude auth status` helper that already exists (`run_claude_auth_status` in `usage/cli/direct.py`).
2. **Login/discovery** `src/ai_usage/providers/claude/login/local/usage_app.py`, class `UsageAppLogin(LoginMethod)` with `credential_kind="none"`. `discover()` probes `GET /health` quickly (short timeout, swallow errors). If it returns `ok`, it returns one `DiscoveredAccount(name="ClaudeUsage.app", options={"base_url": ...})`. The `provider add claude app` wizard then works with zero config.
3. **Provider** `ClaudeUsageAppProvider` in `src/ai_usage/providers/claude/provider.py`.
   - Fields: `service="claude"`, `key="app"`, `usage_method=UsageAppUsage()`, `login_methods=(UsageAppLogin(),)`, `experimental=True`, and an icon (reuse a solid icon such as `gauge`).
   - `configuration_fields`: `base_url` (string, default `http://127.0.0.1:47291`) and `email` (string, optional, help: "defaults to the `claude auth status` email").
   - `user_identity()` returns `canonical_login(email option or the fetched identity.email)`. If neither is available, raise `ProviderLoginError` with a hint to pass `--email`.
4. **Registry**: import the new provider and add it to the tuple in `src/ai_usage/providers/registry.py` (`built_in_registry()`). Optionally export it from `providers/claude/__init__.py`.
5. **Optional**: add a `seven-days-opus` entry to `METRIC_ICONS` in `src/ai_usage/graph.py` only if a distinct icon is wanted. The keyword fallback already gives calendar-week.
6. **Docs**: add a row to the README "Collection methods" table and a `--base-url` / `--email` note. No frontend changes are needed.

## Tests (`tests/test_providers.py` style, `respx` + `@pytest.mark.asyncio`)
- All three windows are present, so three metrics are produced with the correct keys and `window_seconds`, and `reset_at` is parsed.
- `/opus` returns 404 `window_unavailable`, so the metric is skipped. All windows unavailable raises `ProviderError`.
- 503 `no_data` and a connection error both raise `ProviderError` with helpful messages.
- Identity: the `email` option wins. Otherwise the monkeypatched `run_claude_auth_status` is used. With neither, `ProviderLoginError`.
- `UsageAppLogin.discover()` returns an account when `/health` is ok and `[]` when the connection fails.
- Wizard test in `tests/test_provider_commands.py`: `provider add claude app` with a mocked `UsageAppLogin`/usage method. Mock the LoginMethod, not the Provider, and isolate `HOME`.

## Verification
- `uv run pytest tests/test_providers.py tests/test_provider_commands.py tests/test_provider_discovery.py` (or the project's equivalent).
- Compare any failures against the baseline branch before blaming this change.
- With the app running, run `ai-usage provider add claude app --no-input` against the real `127.0.0.1:47291`. It needs a real run because there is no tty here. Then check the metrics in the dashboard on port 4458.
