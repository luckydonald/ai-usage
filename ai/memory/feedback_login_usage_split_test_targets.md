---
name: feedback_login_usage_split_test_targets
description: "after login/usage Provider split, monkeypatch/test targets must hit the LoginMethod, not the old Provider-level authenticate/discover_options delegator"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: f1e51145-6bf4-4ee9-9528-eebb474fade6
  modified: 2026-07-24T06:27:44.283Z
---
`ai-usage` `providers/` package: `Provider.authenticate()`/`discover_options()` only delegate to `matching_login_methods()[0]` — legacy single-choice shims. CLI call sites (`cli.py`) rewritten to resolve specific `LoginMethod` via `resolve_login_method()`, call `login_method.authenticate(...)`/`login_method.discover_options(...)` direct. Any test monkeypatching `SomeUsageProvider.authenticate`/`.discover_options` on `Provider` subclass silently stop working (patches method no longer on call path). Test fail downstream, confusing unrelated error — not obvious "monkeypatch target wrong" message.

**Why:** hit during `provider add` wizard build (service → usage-method → login-method chained prompts, [[project_ai_usage_provider_add_wizard]]). 8 tests in `test_provider_commands.py` broke when `provider.authenticate` calls replaced with `login_method.authenticate`. Fix: retarget monkeypatch strings to concrete `LoginMethod` class (e.g. `ai_usage.providers.codex.login.web.cookie_capture.CookieCaptureLogin.authenticate`), not `Provider`.

**How to apply:** refactoring which object's method actually gets called in composed-object design (Provider/LoginMethod/UsageMethod split) — grep test files for monkeypatch/mock targets on *old* delegating class before assume refactor done. Passing tests after such change don't guarantee mock still on hot path.
