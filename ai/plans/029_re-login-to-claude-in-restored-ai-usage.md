# Re-login to Claude in restored `~/.ai-usage`

## Context
`~/.ai-usage` was restored from git. Git only holds `config.yml`, `services/*/*.yml` and `history/`. `local/` (SQLite with encrypted credentials) and `credential.key` are gitignored, so they are gone. The account YAMLs therefore still point at a `credential_id` that no longer exists. Nothing else is lost: history is keyed by the account `id`, which survives in the YAML.

Claude has two accounts configured:
- `019f7a40-53a0-7581-a494-0d5f8abc404d`: `web` provider (claude.ai@t.duebel.cc). Needs a credential, so this is the one to re-login.
- `72fc02a2-0e64-4cb4-89f9-e9e218a6ff07`: `statusline` provider (Abelmannconsulting). Uses the local `claude` CLI login and has no credential_id.

## Do this
1. From the repo (`ai-usage` is not on PATH):
   ```
   cd /Users/user/Documents/programming/Python/ai-usage
   uv run ai-usage provider login --account 019f7a40-53a0-7581-a494-0d5f8abc404d
   ```
   (`src/ai_usage/cli.py:694` `provider_login`.) It opens a login window, test-fetches, stores the credential in a fresh SQLite and a new `credential.key`, and rewrites only `credential_id` in that account's YAML. The account id is unchanged, so new samples append to the existing `history/v1/claude/019f7a40-…/` and the dashboard continues where it stopped.
2. Verify: `uv run ai-usage provider status` and `git -C ~/.ai-usage diff` (should show only `credential_id` changed). Then start the crawler as usual.

## Do NOT
- `provider add claude web`: creates a new account id and splits the history.
- Delete `services/` or `history/`.
- Run login for codex/copilot (inactive, as you said). Their YAMLs and history stay untouched.

## Caveat: statusline account
Its YAML has Linux paths (`profile_dir: /home/user/.claude`, `relay_file: /home/user/.ai-usage/...`). On this Mac they are wrong. If you still want that account, log in with `claude` (as that org) and fix the paths to `/Users/user/...`, then run `ai-usage claude-relay-install 72fc02a2-0e64-4cb4-89f9-e9e218a6ff07`. If the path was just the previous machine's, ask me and I'll edit the YAML. Otherwise ignore it.
