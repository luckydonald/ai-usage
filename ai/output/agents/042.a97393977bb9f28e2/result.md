## Findings

### 1. `webview_login.capture_cookies_via_webview`
- Defined: `src/ai_usage/webview_login.py:93`
- Used in providers:
  - `src/ai_usage/providers/codex.py:34` (import), `:228` (call)
  - `src/ai_usage/providers/claude/api.py:25` (import), `:200` (call)
- Referenced/monkeypatched in tests:
  - `tests/test_provider_commands.py:575`, `:769`
  - `tests/test_providers.py:539`, `:550`, `:565`
  - `tests/test_webview_login.py:10` (import), plus many call sites lines 108–366

### 2. `install_status_relay` / `remove_status_relay` (src/ai_usage/providers/claude/relay.py:22, :79)
- Re-exported: `src/ai_usage/providers/claude/__init__.py:26,67,73`
- Imported in CLI: `src/ai_usage/cli.py:59-60`
- Called from CLI: `src/ai_usage/cli.py:266`, `:1083`, `:1152`, `:1377`, `:1387`
- Test usage: `tests/test_provider_commands.py:242` (monkeypatch on `ai_usage.cli.install_status_relay`); `tests/test_providers.py:26,30` (import), `:928,932,951` (direct calls)

### 3. Provider protocol methods (`discover`, `authenticate`, `discover_options`, `fetch`, `user_identity`) call sites
- `src/ai_usage/provider_discovery.py:90` — `implementation.discover()` (discovery orchestration)
- `src/ai_usage/collector.py:44` — `provider.user_identity(account, result)`
- `src/ai_usage/collector.py:99` — `await provider.fetch(account, credential)`
- `src/ai_usage/cli.py:282` — `provider.fetch(...)`
- `src/ai_usage/cli.py:294` — `provider.user_identity(...)`
- `src/ai_usage/cli.py:573` — `await provider.authenticate(dynamic_options)`
- `src/ai_usage/cli.py:584` — `await provider.discover_options(credential)`
- `src/ai_usage/cli.py:659` — `await provider.authenticate(account.options)`
- `src/ai_usage/cli.py:670` — `await provider.fetch(account, credential)`
- `src/ai_usage/cli.py:690` — `provider.user_identity(account, probe_result)`

So orchestration lives in `cli.py` (CLI commands) plus `collector.py` and `provider_discovery.py` (core layer).

### 4. Tests importing directly from `ai_usage.providers.*`
- `tests/test_provider_discovery.py:13` — `from ai_usage.providers import Provider, ProviderRegistry`
- `tests/test_provider_discovery.py:14` — `from ai_usage.providers.base import DiscoveredAccount`
- `tests/test_progress.py:23` — `from ai_usage.providers import Provider, ProviderRegistry`
- `tests/test_provider_commands.py:20` — `from ai_usage.providers import built_in_registry`
- `tests/test_provider_commands.py:21` — `from ai_usage.providers.base import DiscoveredAccount, ProviderError`
- `tests/test_webview_login.py:9` — `from ai_usage.providers.base import ProviderError`
- `tests/test_providers.py:14` — `from ai_usage.providers.base import ProviderError, ProviderLoginError`
- `tests/test_providers.py:15-32` — `from ai_usage.providers.claude import (...)` (ClaudeStatusProvider, ClaudeWebUsageProvider, install_status_relay, remove_status_relay, etc.)
- `tests/test_providers.py:33-40` — `from ai_usage.providers.codex import (...)` (CodexStatusProvider, CodexWebUsageProvider, codex_model, etc.)
- `tests/test_providers.py:42-...` — `from ai_usage.providers.copilot import (...)` (CopilotBillingProvider, CopilotStatusProvider, copilot_cli_credentials, etc.)

All of these test files will need import path updates if `ai_usage/providers/` is restructured.

### 5. Entry points for `ai_usage.providers` in pyproject.toml
- Not present. `grep -n "entry" pyproject.toml` only matched line 25 (`sentry-sdk[fastapi]` dependency) — no `[project.entry-points]` section exists, and no `setup.cfg` file was found in the repo. Providers appear to be registered via `built_in_registry` (in `src/ai_usage/providers/__init__.py`) rather than package entry points.