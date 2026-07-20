Repo: /home/user/git/luckydonald/ai-usage. This is a Python CLI/backend + Vue frontend for tracking AI coding-tool usage limits (Claude/Codex/Copilot). The CLI is in src/ai_usage/cli.py, with supporting provider-discovery code in src/ai_usage/provider_discovery.py and src/ai_usage/provider_accounts.py.

There's a backlog note (in ai/plans/pending.md) saying: "The TUI library is overkill for those few selection tasks, which can pretty much all be modeled with a few list selections. List lightweight alternatives." I need to find EXACTLY which TUI/terminal-selection library is currently used, and exactly which CLI interactions use it, before I can plan a replacement.

Please investigate and report:
1. What terminal UI / interactive-selection library is imported/used anywhere in src/ai_usage/ (check pyproject.toml / requirements for candidates like `questionary`, `InquirerPy`, `prompt_toolkit`, `rich`, `textual`, `pick`, `simple-term-menu`, `bullet`, `curses`, etc. — search actual imports, not just guesses).
2. Every distinct place in the CLI where it's used for a selection/menu prompt — list each call site with file:line, what it's selecting (e.g. "pick a provider from discovered accounts", "pick which account to merge into"), and whether it's a single-select or multi-select, and whether any of them need more than a flat list (e.g. nested menus, text input combined with selection, confirmation dialogs, checkboxes).
3. How many distinct such call sites exist total — is it really just "a few", as the backlog note claims?
4. Whether the library is used for anything ELSE besides plain list selection (progress bars, colored output, spinners, tables) that a replacement would need to also cover, or whether other libraries already handle those (e.g. does the project already use `rich` or `click`'s own styling for output, separately from the selection library?).
5. Check pyproject.toml for the exact dependency name/version currently used for this purpose.

Report file:line citations for every call site found. This will feed directly into a plan for possibly swapping the library, so be exhaustive rather than a quick guess.