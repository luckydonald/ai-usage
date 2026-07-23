# Canonical provider logins and config-first account management

## Summary

Replace manual `group_id` grouping with a persisted per-config `login: str | None`, populated once from the provider’s first successful setup fetch. `login` is the canonical real-world account key; config UUIDs and all history remain independent. Implement backend/config/CLI changes only, plus a deferred frontend-design document.

## Data model and provider contract

- Add `AccountConfig.login: str | None`; retain legacy `name` only as non-visual compatibility metadata.
- Remove `group_id` behavior: ignore legacy YAML values, drop them on the next config save, remove graph/API synthetic-series grouping, and retire `provider group` / `provider ungroup`.
- Require every `Provider` subclass to implement `user_identity(account, fetch_result) -> str | None`.
  - Codex/Claude web: canonical email.
  - GitHub Copilot billing: configured GitHub username.
  - Claude web: `email|org-uuid` when the selected organization differs from the email; otherwise email alone.
  - Providers without a reliable source return explicit `None`.
- Store `login` only on the first successful fetch. Missing legacy YAML fields are migrated on that fetch; an explicitly persisted `login: null` means known-unknown and is not later overwritten.

## Setup, storage, and CLI

- Make a successful initial fetch mandatory before a new or restored config is finalized; use a provisional config UUID, persist credentials/config/history only after success, and save the resolved `login` (including `null`).
- Keep later collection and re-login from changing an already-resolved login. Failed setup leaves no config, credential, or history.
- Change `provider ls` / `provider list` to show `STATE | SERVICE | PARSER | ACCOUNT | CONFIG`, with `ACCOUNT` as login or `-`, and the UUID last.
- Update status output, selection prompts, confirmations, and success messages to identify configs by service/parser, account login, and final UUID; never use config `name` visually.
- Remove user-facing rename/name aliases and `--name` setup labeling. Keep destructive `provider merge` as the explicit history-moving operation, clearly distinct from account identity.

## Deferred frontend design document

- Add `ai/plans/016_…` documenting, without touching frontend code, the future hierarchy: provider → account login → parser → config UUID → metric.
- Account containers are visual-only groups for equal `(service, login)` values; unknown logins never auto-group, and different Claude organization UUIDs remain distinct.
- Use an account `section`/collapsible container with child parser/config badges, not a literal `fieldset`; group actions select child configs while config actions remain exact.
- Document that no samples, history files, or API series are merged; the existing frontend remains unchanged in this task.

## Test plan

- Model/YAML tests for missing versus explicit-null login, legacy `group_id` cleanup, and independent config UUID/history preservation.
- Provider tests for each required `user_identity` implementation, including Claude email/org-UUID composition and `None` providers.
- CLI tests for mandatory setup fetch, rollback on failed setup, first-fetch-only login persistence, list column order/value fallback, and removal of grouping/name commands.
- Graph/API regression tests proving configs with equal logins remain separate series until the deferred frontend grouping work is implemented.
