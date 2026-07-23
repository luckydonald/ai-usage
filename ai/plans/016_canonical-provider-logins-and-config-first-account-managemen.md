# Canonical provider logins and config-first account management

## Summary

Replace manual `group_id` grouping with a persisted, non-empty per-config `login`. It is the canonical real-world account key; config UUIDs and all history remain independent. Implement backend/config/CLI changes only, plus a deferred frontend-design document.

## Data model and provider contract

- Add `AccountConfig.login: str | None` solely to read legacy configs; newly written configs must contain a non-empty string.
- Remove `group_id` behavior: ignore legacy YAML values, drop them on the next config save, remove graph/API synthetic-series grouping, and retire `provider group` / `provider ungroup`.
- Require every `Provider` subclass to implement `user_identity(account, fetch_result) -> str | None`.
  - Codex/Claude web: canonical email.
  - GitHub Copilot billing: configured GitHub username.
  - Claude web: `email|org-uuid` when organization differs from the email; otherwise email alone.
  - A provider that cannot determine a login returns `None`.
- Legacy missing/null login remains readable. A successful fetch migrates it only when a concrete login is available; serializing a still-unresolved legacy config omits `login` rather than writing `null`.

## Setup, storage, and CLI

- Make a successful initial fetch and concrete provider login mandatory before a new or restored config is finalized. A `None` result aborts setup with a clear unsupported-identity error.
- Use a provisional config UUID; persist credential, config, and initial history only after the fetch and login resolution succeed. Failure leaves no config, credential, or history.
- Change `provider ls` / `provider list` to show `STATE | SERVICE | PARSER | ACCOUNT | CONFIG`, with the UUID last.
- Update management status, selection prompts, confirmations, and success messages to identify configs by service/parser, account login, and config UUID; never display config `name`.
- Remove user-facing rename/name aliases and `--name` setup labeling. Retain destructive `provider merge` as the explicit history-moving operation.

## Deferred frontend design document

- Add `ai/plans/016_…` documenting, without frontend code changes, the future hierarchy: provider → account login → parser → config UUID → metric.
- Account containers are visual-only groups for equal `(service, login)` values; legacy unresolved configs remain separate and visibly unresolved. Different Claude organization UUIDs remain distinct.
- Use an account `section`/collapsible container with child parser/config badges, not a literal `fieldset`; group actions select child configs while config actions remain exact.
- Document that no samples, history files, or API series are merged.

## Test plan

- Model/YAML tests for rejecting newly persisted null/empty login, legacy missing/null compatibility, legacy `group_id` cleanup, and independent config UUID/history preservation.
- Provider tests for every required identity resolver, including Claude email/org-UUID composition and unresolved identity.
- CLI tests for setup rollback when fetch or login resolution fails, successful atomic creation with a concrete login, list column order, and removal of grouping/name commands.
- Graph/API regression tests proving configs with equal logins remain separate series until the deferred frontend grouping work is implemented.
