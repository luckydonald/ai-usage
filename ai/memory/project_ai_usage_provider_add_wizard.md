---
name: project_ai_usage_provider_add_wizard
description: "ai-usage cli.py provider-add flow was reworked into chained service -> usage-method -> login-method prompts, built on the earlier Provider/LoginMethod/UsageMethod split"
metadata: 
  node_type: memory
  type: project
  originSessionId: f1e51145-6bf4-4ee9-9528-eebb474fade6
  modified: 2026-07-24T06:27:55.210Z
---

`src/ai_usage/cli.py`'s `ai-usage provider add`/`provider login` flow used to pick a provider from one flat `service/key: display_name` list and silently use `matching_login_methods()[0]`. Reworked (commit `d59697e`, on branch `mane`) into: pick service -> pick usage-method (skipped if only one candidate) -> resolve login-method (prompted only if a provider has more than one matching `LoginMethod`).

Key additions in `cli.py`: `select_provider(registry)`, `resolve_login_method(provider)`. `select_discovered_account` now resolves the provider up front via `select_provider` when either `service`/`provider_key` is missing, then discovery is always scoped to that one resolved provider (skips straight to manual config if nothing discovered, no empty prompt). `print_discovery_choices`'s "Manual provider adapters:" listing is now grouped by service instead of one flat line per provider.

**Why:** built on top of an earlier session's larger restructuring that split `providers/<provider>/{login,usage}/<type>/<method>.py` into composable `LoginMethod`/`UsageMethod` objects (see [[feedback_login_usage_split_test_targets]] for the test-target gotcha this surfaced) — the wizard was explicitly deferred out of that first commit (`da98173`) as follow-up work.

**How to apply:** every built-in provider today has 0 or 1 matching login methods, so the login-method prompt is currently a no-op — it's the seam for a future provider shipping >=2 alternatives per `credential_kind`. If asked to add a new provider with multiple login sources, this wizard already supports it without further `cli.py` changes.
