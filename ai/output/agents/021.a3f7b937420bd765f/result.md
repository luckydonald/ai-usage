## Findings

### 1. Which TUI library is used

**`textual>=5.3`** is the only interactive-selection/TUI library in the project, declared in `pyproject.toml` (dependencies list, alongside `click>=8.2` and `typer>=0.15`). No `questionary`, `InquirerPy`, `prompt_toolkit`, `rich`, `pick`, `simple-term-menu`, `bullet`, or `curses` usage exists anywhere in `src/ai_usage/`.

It's wrapped in a small custom module: `/home/user/git/luckydonald/ai-usage/src/ai_usage/provider_tui.py` (63 lines total):

- `SelectionChoice` dataclass (`key`, `label`, `detail`) — line 12
- `SelectionApp(App[str | None])` — a full-screen Textual `App` with `Header`, `Footer`, and a single `OptionList` widget — lines 19-54
- `select_choice(title, choices) -> str | None` — async helper that instantiates and runs `SelectionApp` via `run_async()` — lines 58-63

This is imported once in the CLI: `src/ai_usage/cli.py:51` — `from ai_usage.provider_tui import SelectionChoice, select_choice`.

### 2. Every call site of `select_choice` in `cli.py`

All are single-select, flat-list menus (Textual's `OptionList` is single-selection only; there is no multi-select/checkbox widget in use). No call site combines free-text input with the selection screen itself — text input (`click.prompt`) always happens as a separate, subsequent step outside the Textual app.

1. **`cli.py:349`** — `select_choice("Choose an account to add", options)` inside `select_discovered_account()` (line 331). Selects a *discovered account* (built from `DiscoveryChoice` results) or falls through to a "Manually configure other…" sentinel option. Single-select, flat list.
2. **`cli.py:365`** — `select_choice("Choose a provider adapter", manual_options)`, same function, second-stage picker used only when the user picked "Manually configure other…" in call site 1. Selects a `(service, provider_key)` pair. Single-select, flat list. — **This is effectively a nested/cascading menu**: site 1 conditionally leads into site 2.
3. **`cli.py:623`** — inside `ensure_host_identity()` → nested `choose_among()` closure (line 620). Selects which of several ambiguous registered `host_id` candidates to restore, or "None, generate new". Single-select, flat list. (Also uses `click.confirm` right above it at line 617 for a yes/no restore confirmation — a separate, non-Textual interaction.)
4. **`cli.py:678`** — inside `run_first_crawl_wizard()` (an actual `while True:` wizard loop, line 667-698). Top-level menu: "Enable existing service on this device" / "Create new" / "Done/Exit". Single-select, flat list.
5. **`cli.py:688`** — same wizard function, nested sub-menu invoked when the user picks "enable" in call site 4: lists configured accounts (`{service}/{provider} — {name}`) plus a "« back" option. Single-select, flat list. — **Call sites 4+5 form a genuine nested-menu / mini state machine** (the `while True` loop re-shows the top menu after the sub-menu resolves).
6. **`cli.py:788`** — inside `resolve_account()` (starts line ~760s). `select_choice(f"Choose an account to {action}", [...])` — generic "pick one configured account" picker reused for remove/merge-from/merge-into flows. Single-select, flat list.

**Total: 6 distinct `select_choice(...)` call sites**, but note two of them (`#1`/`#2` and `#4`/`#5`) are conditionally-chained/nested rather than independent flat pickers — so structurally there are 4 independent decision points, 2 of which branch into a second-level picker.

### 3. Non-selection interactive prompts (click, not Textual) that would also matter for a replacement plan

These aren't Textual but are part of the same "interactive CLI" surface and should be considered when picking a lighter selection library (to keep a consistent look/feel):

- `cli.py:169` — `click.prompt(field.label, hide_input=field.kind == "secret")` — free-text/secret input for missing required provider config fields.
- `cli.py:617` — `click.confirm(...)` — yes/no confirm to restore host identity.
- `cli.py:949` — `click.confirm(...)` — yes/no confirm to also delete historical usage on account removal.
- `cli.py:1055` — `click.confirm(...)` — yes/no confirm before merging/deleting account history.

So counting *all* interactive decision points (selects + confirms + prompts), there are 10 call sites, not "a few" in the sense of one or two — but the backlog note's core claim ("can pretty much all be modeled with a few list selections") is largely accurate: every Textual call site is a flat single-select `OptionList`, no checkboxes/multi-select, no in-menu text entry, no progress/spinner use of Textual. The two "nested" cases (add-account and first-crawl wizard) are just sequential single-selects chained in application logic (a loop / conditional), not a Textual feature (e.g., no `Screen` stack, no modal dialogs) — so a plain "call a list-picker function repeatedly" replacement would handle them fine.

### 4. Is Textual used for anything besides selection (progress bars, colored output, spinners, tables)?

No. Grep across `src/ai_usage/*.py` confirms:
- `textual` is imported only in `provider_tui.py` (the picker) and referenced only in a comment in `host_identity.py:124` (no actual import).
- All colored/status output in the CLI goes through plain `click.echo(...)` (many sites, e.g. `cli.py:242-310`, `429-599`, `663-732`, etc.) — no `rich.Console`, no `click.secho`/ANSI styling helpers, no progress bars, no spinners, no tables via any TUI/rich library. `print_accounts()` (referenced at `cli.py:778`, `782`) just does fixed-width `click.echo` formatting (see header format at line 730: `f"{'STATE':<10} {'SERVICE/PROVIDER':<30} {'NAME':<24} ACCOUNT"`).
- So a replacement library only needs to cover single-select flat-list menus with an optional detail/subtext line per option (used for "detail" in `SelectionChoice`) and cancel-on-escape behavior (`action_cancel` in `provider_tui.py:52-54`, bound to `escape` at line 24). No progress-bar/table/spinner functionality needs to be preserved from Textual.

### 5. Exact dependency

`pyproject.toml` line: `"textual>=5.3",` inside the top-level `[project] dependencies` list (not in an optional-dependencies group — it's a hard runtime dependency for all installs, even the FastAPI backend/API-only use cases).

### Summary answer to "is it really just a few?"

Yes — structurally there are only 4 independent Textual-picker decision points (`select_discovered_account`'s two-stage picker, `ensure_host_identity`'s ambiguous-host picker, `run_first_crawl_wizard`'s two-stage wizard menu, and `resolve_account`'s generic account picker), realized across 6 `select_choice(...)` call sites, all single-select flat lists with no checkboxes, no in-line text entry, and no modal/nested Textual screens. The backlog note's framing holds up: this is a strong candidate to replace with a lightweight single-select list-picker library (or even a simple `click`-based numbered-menu helper), without needing to preserve any Textual-specific chrome (headers/footers/CSS) or cover progress bars/tables/spinners, since those are already handled elsewhere (plain `click.echo`) and never routed through Textual.