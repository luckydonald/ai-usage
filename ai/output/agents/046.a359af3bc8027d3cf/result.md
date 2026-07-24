That remaining failure is in copilot territory (another agent's in-progress work), unrelated to my claude changes. My task is complete.

## Summary

Restructured Claude provider files into the login/usage split under `src/ai_usage/providers/claude/`:

**New files created:**
- `_shared.py` — `claude_environment`, `claude_profile_path`, `canonical_claude_profile_dir`, `claude_default_profile`, `claude_setup_required_message`, `write_claude_error_log`, `claude_cli_failure_message` (moved verbatim from `claude_cli.py`)
- `login/local/settings_file.py` — `SettingsFileLogin(LoginMethod)`, `credential_kind="none"`
- `login/web/cookie_capture.py` — `CookieCaptureLogin(LoginMethod)`, `credential_kind="cookie_jar"` (authenticate + discover_options / org lookup)
- `usage/web/private_api.py` — `PrivateApiUsage(UsageMethod)`, `required_credential_kind="cookie_jar"`, plus all payload models/parsers (`parse_claude_web_usage`, `extract_claude_web_notes`, `get_json`, `describe_fetch_failure`, `reauth_hint`, etc.)
- `usage/local/relay_file.py` — `RelayFileUsage(UsageMethod)`, `required_credential_kind="none"`, plus `parse_status_payload`
- `usage/cli/direct.py` — `DirectCliUsage(UsageMethod)`, `run_claude_usage_direct`, `run_claude_auth_status`, and the terminal-output parsing helpers (`parse_usage_output`, `claude_metric_key`, `claude_metric_model`, `extract_claude_notes`, `normalize_claude_terminal_output`, `ANSI_PATTERN`, `SECTION_PATTERN`, `PROMO_PATTERN`)
- `usage/cli/interactive.py` — `InteractiveCliUsage(UsageMethod)`, `run_claude_usage` (pexpect PTY), reusing parsing helpers from `direct.py`
- `provider.py` — assembles `ClaudeWebUsageProvider` (CookieCaptureLogin + PrivateApiUsage), `ClaudeStatusProvider` (SettingsFileLogin + `FallbackUsageMethod((RelayFileUsage(), DirectCliUsage(), InteractiveCliUsage()))`), `ClaudeUsageProvider` (CLI-only fallback: `FallbackUsageMethod((DirectCliUsage(), InteractiveCliUsage()))`, subclass of `ClaudeStatusProvider` stripping `relay_file` option as before)
- `__init__.py` rewritten to re-export the same public names as before (kept old class/function names since `cli.py`/`registry.py` are off-limits and still import them by these names)
- `relay.py` — kept as-is except its one import updated to `ai_usage.providers.claude._shared`

**Deleted:** `providers/claude_cli.py`, `providers/claude_direct.py`, `providers/claude_interactive.py`, `providers/claude/api.py`, `providers/claude/status.py`.

**Test updates (`tests/test_providers.py`, claude-only edits):** updated the claude import block to `ai_usage.providers.claude`, and updated all `monkeypatch.setattr` string targets that pointed at the deleted `claude.api`/`claude.status`/`claude_cli` module paths to their new locations. Notably, since `run_claude_auth_status` is now imported independently into three separate modules (`usage/local/relay_file.py`, `usage/cli/direct.py`, `usage/cli/interactive.py`) rather than one shared call site, tests exercising the full statusline fallback chain now patch it in each module that's reachable in that test, instead of a single location.

**Deviation from plan:** kept the old class names (`ClaudeStatusProvider`, `ClaudeUsageProvider`, `ClaudeWebUsageProvider`) and helper/function names in `providers/claude/__init__.py` rather than renaming, because `src/ai_usage/cli.py` and `src/ai_usage/providers/registry.py` are off-limits (owned by other in-flight agents) and still import these exact names from `ai_usage.providers.claude`; renaming would have broken those files without being able to fix them.

**Verification:**
- `uv run python -c "from ai_usage.providers.claude.provider import *"` — succeeds.
- `grep -rn "claude_cli\|claude_direct\|claude_interactive" src/ tests/` — no remaining references except the intentionally-kept `claude_cli_failure_message`/`claude_default_profile` names.
- `uv run pytest tests/test_providers.py -k claude -q` — 33 passed.
- Full `tests/test_providers.py` run has one unrelated failure (`test_copilot_status_provider_fetch`) in the copilot subsystem still being migrated by another agent — not related to this Claude split.