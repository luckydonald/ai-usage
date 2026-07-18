Repo /home/user/git/luckydonald/ai-usage. Read-only research, quick.

I'm about to add Pydantic models to src/ai_usage/providers/claude.py and codex.py that parse web-API JSON responses, with a fallback: if pydantic validation fails, log/emit a warning and fall back to manual dict.get()-style access on the raw parsed JSON for the fields actually needed.

Report:
1. Does the codebase use Python's `warnings` module, `logging` module, or something else (e.g. a custom `report`/reporter callback already passed into providers) anywhere currently for non-fatal issues? Grep `import warnings`, `import logging`, `logger =`, across src/ai_usage/.
2. Is there an existing "reporter" callback pattern passed into providers already (I recall `Provider.fetch()` doesn't take a reporter param based on base.py's signature `fetch(self, account, credential)` — confirm this is still true) so a warning would have to go through Python's `warnings.warn()` or similar rather than the progress reporter.
3. Check pydantic version pinned (pyproject.toml already shows `pydantic>=2.11`) and how existing models.py defines models (BaseModel style, any `model_config` usage, `ConfigDict` imports) so new models match existing style exactly.

Keep under 100 lines, cite file:line.