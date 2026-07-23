# Canonical provider logins with compatibility graph grouping

## Summary

Replace persisted manual `group_id` with a persisted, non-empty per-config `login`. Use `(service, login)` to retain today’s synthesized graph grouping for the unchanged dashboard, while config UUIDs, parsers, and histories remain separate. Implement backend/config/CLI changes plus a deferred frontend-design document.

## Data model and provider contract

- Add `AccountConfig.login: str | None` solely to read legacy configs; every newly written config must contain a non-empty string.
- Remove persisted `group_id`: ignore legacy YAML values and drop them on the next config save. `login` is the only persisted account-association key.
- Add required `Provider.user_identity(account, fetch_result) -> str`.
  - Base implementation raises `NotImplementedError`; built-in and plugin providers must override it.
  - Providers that cannot determine a login raise a dedicated provider-login error.
  - Codex/Claude web return canonical email; GitHub Copilot billing returns configured GitHub username; Claude web returns `email|org-uuid` when organization differs from the email, otherwise email alone.
- Legacy missing/null login remains readable. A successful fetch migrates it only after `user_identity()` succeeds; unresolved legacy configs serialize without a `login` key, never with `null`.

## Setup, storage, and CLI

- Require a successful initial fetch and `user_identity()` result before a new or restored config is finalized. Use a provisional config UUID; persist credential, config, and initial history only after both succeed.
- Leave no config, credential, or history after fetch or login-resolution failure.
- Change `provider ls` / `provider list` to show `STATE | SERVICE | PARSER | ACCOUNT | CONFIG`, with account login before the final UUID.
- Update management status, prompts, confirmations, and success messages to identify configs by service/parser, account login, and config UUID; never display config `name`.
- Remove user-facing rename/name aliases and `--name` setup labeling. Retain destructive `provider merge` for actual history movement.

## Current graph compatibility and deferred frontend design

- Preserve the current synthesized-series behavior for the unchanged frontend, but derive groups at API/graph time from configs sharing the same non-empty `(service, login)`.
- Generate a deterministic internal graph-group key from service plus login; expose it as the existing catalog `group_id` compatibility field only when two or more configs share that key. It is never persisted to YAML.
- Keep current conflict handling (`max` for coincident samples) as display-only aggregation; source histories and config UUIDs remain untouched.
- Add `ai/plans/016_…` documenting the later replacement UI: provider → account login → parser → config UUID → metric. It will use visual account containers and child config badges, preserving individual streams instead of synthetic series.

## Test plan

- Model/YAML tests for rejecting newly persisted null/empty logins, legacy login/group-id compatibility, and independent config UUID/history preservation.
- Provider tests for required login resolution, missing implementation, unavailable-login errors, and Claude email/org-UUID composition.
- CLI tests for atomic setup rollback, concrete-login creation, list column order, and removal of grouping/name commands.
- Graph/API tests that same-service equal-logins synthesize the current single display series and catalog group key; different services, different Claude organizations, and legacy unresolved configs stay separate.
