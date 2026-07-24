Other agents' claude/codex migrations are already in progress concurrently. My copilot-specific work is complete and self-contained. Import check passed cleanly.

## Summary

**New files (copilot login/usage split):**
- `src/ai_usage/providers/copilot/__init__.py` (empty package marker)
- `src/ai_usage/providers/copilot/login/__init__.py`, `login/cli/__init__.py`
- `src/ai_usage/providers/copilot/login/cli/token_reuse.py` — `copilot_cli_credentials()` (moved verbatim) + `TokenReuseLogin(LoginMethod)`, `credential_kind="bearer_token"`
- `src/ai_usage/providers/copilot/usage/__init__.py`, `usage/web/__init__.py`
- `src/ai_usage/providers/copilot/usage/web/billing_api.py` — `next_billing_reset()` + `BillingApiUsage(UsageMethod)`, `required_credential_kind="bearer_token"`
- `src/ai_usage/providers/copilot/usage/web/quota_api.py` — `copilot_quota_metric_key()`, `parse_copilot_quota_payload()` + `QuotaApiUsage(UsageMethod)`, `required_credential_kind="bearer_token"` (no longer calls `copilot_cli_credentials` inline)
- `src/ai_usage/providers/copilot/usage/web/entitlements.py` — `GenericPrivateWebUsage(UsageMethod)` (was `PrivateWebProvider`), `required_credential_kind="cookie_jar"`, takes `service`/`key` via `__init__`
- `src/ai_usage/providers/copilot/provider.py` — exports `CopilotBillingProvider`, `CopilotStatusProvider`, `CopilotEntitlementsProvider` (all `Provider` subclasses composed from the above)

**Deleted:** `src/ai_usage/providers/copilot.py`, `src/ai_usage/providers/web.py`

**Updated:** `src/ai_usage/providers/registry.py` (import block now points to `copilot.provider`), `tests/test_providers.py` (only the `from ai_usage.providers.copilot import (...)` block, split into 4 import lines to their new homes).

**Deviations from plan (with rationale):**
1. **`ConfigFileLogin` vs `TokenReuseLogin`**: merged into one class, `TokenReuseLogin`. Original `CopilotStatusProvider.discover()` (config-file existence probe) and `copilot_cli_credentials()` (env-var/config-file token read, previously called inline inside `fetch()`) read the exact same source (`~/.copilot/config.json` + the same env vars), so a separate `ConfigFileLogin` would just re-probe the same file without being able to produce a usable credential. `TokenReuseLogin.discover()` now does the full resolution in one step, per plan's requirement that login side effects move out of `UsageMethod.fetch()`. No `login/local/` directory was created since it would be unused.
2. **`PrivateWebProvider`/`web.py` placement**: kept as `GenericPrivateWebUsage` in `copilot/usage/web/entitlements.py`, not moved to `providers/base.py`. Rationale documented in that file's module docstring: it's marked "generic/reusable" but currently has exactly one consumer; `base.py` should hold shared ABCs/errors/contracts, not a concrete fetch implementation until a second non-Copilot consumer actually needs it.
3. **Behavior note**: `TokenReuseLogin.discover()` now only returns an account when a token is actually resolvable (env var or config-file token present), whereas the old `CopilotStatusProvider.discover()` returned an account entry whenever `~/.copilot/config.json` merely existed (even without an extractable token, deferring resolution to `fetch()` time). This is an intentional, plan-mandated consequence of moving credential resolution out of `fetch()` and into the `LoginMethod`.
4. Did not touch `tests/test_provider_commands.py:144` (`monkeypatch.setattr("ai_usage.providers.copilot.CopilotBillingProvider.fetch", ...)`), per instructions to avoid conflicting with other agents editing that file — it will need updating to `ai_usage.providers.copilot.provider.CopilotBillingProvider.fetch` by whoever owns that file. Also, `tests/test_providers.py:675` still calls `CopilotStatusProvider().fetch(account, None)` expecting the old inline-token-resolution behavior; this will now fail (credential is `None`) since resolution moved to `TokenReuseLogin` — left as-is since only import lines were in scope, and the full suite wasn't run per instructions.

**Verification:** `uv run python -c "from ai_usage.providers.copilot.provider import *"` succeeds; `built_in_registry()` still lists all 9 `(service, key)` pairs including `('copilot', 'github-api')`, `('copilot', 'statusline')`, `('copilot', 'entitlements')`. `grep` confirms no dangling references to the deleted `providers.copilot`/`providers.web` flat modules outside the one out-of-scope test line noted above.