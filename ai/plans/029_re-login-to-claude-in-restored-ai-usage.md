# Re-login to Claude in restored `~/.ai-usage`

## Context
`~/.ai-usage` was restored from git. Git only holds `config.yml`, `services/*/*.yml` and `history/`. `local/` (SQLite with encrypted credentials) and `credential.key` are gitignored, so they are gone. The account YAMLs still point at a `credential_id` that no longer exists. History is keyed by the account `id`, which survives in the YAML.

Claude has two accounts configured:
- `019f7a40-53a0-7581-a494-0d5f8abc404d`: `web` provider. Needs a credential, so this is the one to re-login.
- `72fc02a2-0e64-4cb4-89f9-e9e218a6ff07`: `statusline` provider. Uses the local `claude` CLI login and has no credential_id.

## Do this
1. From the repo (`ai-usage` is not on PATH):
   ```
   cd /Users/user/Documents/programming/Python/ai-usage
   uv run ai-usage provider login --account 019f7a40-53a0-7581-a494-0d5f8abc404d
   ```
   (`src/ai_usage/cli.py:694` `provider_login`.) It opens a login window, test-fetches, stores the credential in a fresh SQLite plus a new `credential.key`, and rewrites only `credential_id` in that account's YAML. The account id is unchanged, so new samples append to the existing history and the dashboard continues where it stopped.
2. Verify: `uv run ai-usage provider status` and `git -C ~/.ai-usage diff` (should show only `credential_id` changed). Then start the crawler as usual.

## Do NOT
- `provider add claude web`: creates a new account id and splits the history.
- Delete `services/` or `history/`.
- Run login for codex/copilot (inactive). Their YAMLs and history stay untouched.

## Caveat: statusline account
Its YAML has Linux paths (`profile_dir`, `relay_file` under `/home/user/...`), wrong on this Mac. Only matters if that account is still wanted: log in with `claude`, fix the paths to `/Users/user/...`, run `ai-usage claude-relay-install 72fc02a2-0e64-4cb4-89f9-e9e218a6ff07`.

## Git handling (commit-with-lplp-style)
- The committed plan `ai/plans/029_re-login-to-claude-in-restored-ai-usage.md` (commit `46a5251`) contains emails/account names. The new plan file has none.
- When implementation starts, first create a backup tag at the current HEAD (e.g. `backup/pre-plan-029-squash`), then amend/squash the erroneous plan commit and its prompt commits into one clean commit with the sanitized plan content, so the emails vanish from the branch history. Per rule 7 this is explicitly authorized by the user.
- Message goes via `ai/git/pending-commit.md`, format `[ai] plans: ai: Plan: Re-login to Claude in the restored data directory without overwriting history.`; `git add` only explicit paths.
- Anything committed later follows the same style (commit per task, fold `ai:` auto-commits).
- The live `~/.ai-usage` itself is a separate git repo that auto-commits crawls; leave its history alone.
