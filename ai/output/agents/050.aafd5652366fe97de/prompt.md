In repo /home/user/git/luckydonald/ai-usage, investigate the provider/login/usage-method architecture used to add new AI-usage providers (e.g. Claude, Codex, Cursor, etc.).

Report:
1. Directory layout for providers (e.g. src/.../providers/<name>/ or similar) — list existing provider names/directories.
2. The composition pattern: how a "Provider" is built from a "LoginMethod" + "UsageMethod" (per memory: "provider add wizard" chains service→usage-method→login-method prompts, commit d59697e in cli.py). Find and read cli.py's add-wizard code, and the base classes/interfaces for LoginMethod and UsageMethod (file paths + key method signatures).
3. For 2-3 existing fully-implemented providers (pick ones with OAuth login + JSON API usage-method, similar to Claude/Codex), show the concrete file paths and roughly how login.py/usage.py (or equivalent) are structured — enough detail to replicate the pattern for a new provider.
4. Any existing provider stubs that are incomplete/TODO (partially implemented) — list them with file paths.
5. Any existing generic/shared HTTP client, OAuth PKCE helper, or credential storage utilities that new providers should reuse (file paths + brief description).

Be thorough — this repo builds providers for parsing AI usage/quota data, similar in spirit to the referenced IntelliJ plugins llm-subscription-usage-intellij and tokenpulse. Return concrete file:line references throughout.