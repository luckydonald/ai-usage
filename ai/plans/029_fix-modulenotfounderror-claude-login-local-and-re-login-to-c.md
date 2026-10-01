# Fix `ModuleNotFoundError: ...claude.login.local` and re-login to Claude in restored `~/.ai-usage`

## Context
`~/.ai-usage` was restored from git (only `config.yml`, `services/*/*.yml`, `history/`; `local/` SQLite and `credential.key` are gitignored, so gone). The Claude web account `019f7a40-53a0-7581-a494-0d5f8abc404d` therefore has a dangling `credential_id` and needs `provider login`.

`uv run ai-usage provider login --account 019f7a40-…` fails with `No module named 'ai_usage.providers.claude.login.local'`.

**Root cause (verified):** the repo's own `.gitignore:39` has `[Ll]ocal` (from the Python venv template), which ignores *every* directory named `local`. Commit `da98173` (provider login/usage split) created three modules in `local/` dirs, and they were never committed (`git ls-files | grep /local/` is empty; no history contains them). They died with the old setup, yet are imported:
- `src/ai_usage/providers/claude/login/local/settings_file.py`: `SettingsFileLogin` (key `settings_file`, display "Local Claude CLI settings", `credential_kind="none"`, probes `~/.claude` settings/profile for discovery)
- `src/ai_usage/providers/claude/usage/local/relay_file.py`: `RelayFileUsage` (`required_credential_kind="none"`) plus `parse_status_payload`; reads the status-line relay file
- `src/ai_usage/providers/codex/login/local/auth_json.py`: `AuthJsonLogin` (key `local-auth-json`, display "Reuse local auth.json", `credential_kind="app_token"`, probes `~/.codex/auth.json`, returns `options.profile_dir`)

## Plan
1. **Gitignore fix first:** add `!src/ai_usage/providers/**/local/` (negation, after line 39) so these directories can be tracked. Verify with `git check-ignore -v`.
2. **Reconstruct the three modules.** Sources: the pre-split code at `git show da98173^:src/ai_usage/providers/claude/status.py`, `.../claude_cli.py` and `.../codex.py`, which hold the relay parsing, settings probing and auth.json probing logic. Descriptions of the intended shape are in `ai/output/agents/046.*/result.md`, `045.*/result.md`, `050.*/result.md`. Contracts: `LoginMethod`/`UsageMethod` in `src/ai_usage/providers/base.py:50-87`. Match sibling modules (`login/web/cookie_capture.py`, `usage/cli/direct.py`, `codex/usage/cli/app_server.py`) for style, and import helpers from `claude/_shared.py`. Add the missing `__init__.py` in each new `local/` package.
3. **Verify code:** `uv run python -c "import ai_usage.providers.registry"`, `uv run pytest tests/test_providers.py tests/test_provider_commands.py -q` (existing tests already import/patch `relay_file`, so they check the reconstruction; compare against the previously reported baseline of only pre-existing unrelated failures).
4. **Re-login (web account only):**
   ```
   uv run ai-usage provider login --account 019f7a40-53a0-7581-a494-0d5f8abc404d
   ```
   (`cli.py:694`.) Opens a login window, test-fetches, stores the credential in a fresh SQLite and new `credential.key`, and rewrites only `credential_id` in that account's YAML. Account id unchanged, so history continues. Then `uv run ai-usage provider status` and `git -C ~/.ai-usage diff` (should show only `credential_id`).
5. **Do NOT:** `provider add claude web` (new id, splits history), delete `services/`/`history/`, or touch codex/copilot accounts (inactive).

## Caveat: statusline account
`72fc02a2-0e64-4cb4-89f9-e9e218a6ff07` has Linux paths (`profile_dir`, `relay_file` under `/home/user/...`), wrong on this Mac. Only matters if still wanted: fix to `/Users/user/...` and run `ai-usage claude-relay-install 72fc02a2-0e64-4cb4-89f9-e9e218a6ff07`.

## Git handling (commit-with-lplp-style)
- Plan commit `46a5251` (`ai/plans/029_…`) contains emails/account names. The plan files must not mention them. When implementation starts: first create a backup tag at current HEAD (e.g. `backup/pre-plan-029-squash`), then amend/squash that erroneous plan commit with its prompt commits into one clean `[ai] plans: ai: Plan: …` commit with the sanitized plan (authorized by the user).
- Then commit per task, separately:
  1. `[git] ignore rules: ai: Run: Un-ignored provider `local/` packages.` (`.gitignore` only)
  2. `[backend] providers: ai: Run: Recreated the untracked `local/` login/usage modules.` (three modules + `__init__.py`s)
- Messages via `ai/git/pending-commit.md`, explicit `git add` paths, fold `ai:` auto-commits, no hard-wrapping.
- `~/.ai-usage` is its own auto-committing repo; leave its history alone.
