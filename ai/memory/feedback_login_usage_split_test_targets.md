---
name: feedback_login_usage_split_test_targets
description: "after login/usage Provider split, monkeypatch/test targets must hit the LoginMethod, not the old Provider-level authenticate/discover_options delegator"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: f1e51145-6bf4-4ee9-9528-eebb474fade6
  modified: 2026-07-24T06:27:44.283Z
---

In `ai-usage`'s `providers/` package, `Provider.authenticate()`/`discover_options()` only ever delegate to `matching_login_methods()[0]` — they are legacy single-choice shims. Once CLI call sites (`cli.py`) are rewritten to resolve a specific `LoginMethod` via `resolve_login_method()` and call `login_method.authenticate(...)`/`login_method.discover_options(...)` directly, any test that monkeypatches `SomeUsageProvider.authenticate`/`.discover_options` on the `Provider` subclass silently stops taking effect (it patches a method that's no longer on the call path) and the test fails downstream with a confusing unrelated error, not an obvious "monkeypatch target wrong" message.

**Why:** happened while implementing the `provider add` wizard (service → usage-method → login-method chained prompts, [[project_ai_usage_provider_add_wizard]]) — 8 tests in `test_provider_commands.py` broke when `provider.authenticate` calls were replaced with `login_method.authenticate`. Fix was retargeting monkeypatch strings to the concrete `LoginMethod` class (e.g. `ai_usage.providers.codex.login.web.cookie_capture.CookieCaptureLogin.authenticate`), not the `Provider`.

**How to apply:** whenever refactoring which object's method actually gets called in a composed-object design (Provider/LoginMethod/UsageMethod split), grep test files for monkeypatch/mock targets on the *old* delegating class before assuming the refactor is done — passing tests after such a change don't guarantee the mock is still on the hot path.
