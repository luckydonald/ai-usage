---
name: project_ai_usage_provider_add_wizard
description: "ai-usage cli.py provider-add flow was reworked into chained service -> usage-method -> login-method prompts, built on the earlier Provider/LoginMethod/UsageMethod split"
metadata: 
  node_type: memory
  type: project
  originSessionId: f1e51145-6bf4-4ee9-9528-eebb474fade6
  modified: 2026-07-24T06:27:55.210Z
---
`ai-usage provider add`/`provider login` in `src/ai_usage/cli.py` used pick provider from flat `service/key: display_name` list, silent use `matching_login_methods()[0]`. Reworked (commit `d59697e`, branch `mane`) into: pick service -> pick usage-method (skip if only one candidate) -> resolve login-method (prompt only if provider has 2+ matching `LoginMethod`).

Key additions in `cli.py`: `select_provider(registry)`, `resolve_login_method(provider)`. `select_discovered_account` now resolve provider up front via `select_provider` when `service`/`provider_key` missing, then discovery always scoped to that one resolved provider (skip straight to manual config if nothing discovered, no empty prompt). `print_discovery_choices`'s "Manual provider adapters:" listing now grouped by service, not one flat line per provider.

**Why:** built on earlier session's bigger restructuring that split `providers/<provider>/{login,usage}/<type>/<method>.py` into composable `LoginMethod`/`UsageMethod` objects (see [[feedback_login_usage_split_test_targets]] for test-target gotcha this surfaced) — wizard explicitly deferred out of first commit (`da98173`) as follow-up.

**How to apply:** every built-in provider today got 0 or 1 matching login methods, so login-method prompt currently no-op — seam for future provider shipping 2+ alternatives per `credential_kind`. Asked to add new provider with multiple login sources: wizard already support it, no further `cli.py` changes needed.
