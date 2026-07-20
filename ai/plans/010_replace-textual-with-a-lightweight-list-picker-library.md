# Replace Textual with a lightweight list-picker library

## Context
`ai/plans/pending.md` has carried a note for a while: "The TUI library is overkill for those few selection tasks, which can pretty much all be modeled with a few list selections. List lightweight alternatives." Investigated to confirm the claim rather than guess, then researched real replacement options.

## What's actually there today (confirmed via code read)
- **`textual>=5.3`** is a hard runtime dependency in `pyproject.toml` (top-level `[project] dependencies`, not optional) — pulled in even for API-only/backend-only installs.
- It's wrapped in one small module, `src/ai_usage/provider_tui.py` (63 lines): a `SelectionChoice(key, label, detail)` dataclass, a full-screen `SelectionApp(App[str | None])` (Header + Footer + a single `OptionList`), and an async `select_choice(title, choices) -> str | None` helper.
- **6 call sites** in `src/ai_usage/cli.py`, all going through that one `select_choice()` helper — `provider_discovery`'s account/adapter picker (`cli.py:349`, `:365`, two-stage), `ensure_host_identity`'s ambiguous-host picker (`:623`), `run_first_crawl_wizard`'s top-menu/sub-menu (`:678`, `:688`, a `while True:` wizard loop), and `resolve_account`'s generic account picker (`:788`).
- **Every single one is a flat, single-select list** with an optional one-line detail/subtext per option and cancel-on-escape. No checkboxes, no multi-select, no in-menu text entry, no modal/nested Textual screens — the "nested menus" that exist are just sequential single-selects chained by plain Python control flow (loops/conditionals), not a Textual feature.
- Textual is used for **nothing else** in the project — no progress bars, spinners, or tables route through it. All other CLI output is plain `click.echo`, and the other interactive prompts (`click.prompt` for text/secret input, `click.confirm` for yes/no) are already plain `click`, not Textual.
- Conclusion: the backlog note holds up. This is a full-screen TUI framework (widgets, CSS-like styling, a `Screen` stack, its own event loop integration) pulled in solely to render single-select flat menus with a description line — a plain inline list-picker library covers 100% of the actual usage with much less dependency weight and no `run_async()`/event-loop integration overhead.

## Alternatives considered
| Library | Fit | Notes |
|---|---|---|
| **`questionary`** (recommended) | Exact match | Built on `prompt_toolkit`. Inline `questionary.select(message, choices).ask()` — one call, no full-screen app, no CSS. `Choice(title, value)` maps directly onto `SelectionChoice(label, key)`; the `detail` line can be folded into the choice title (e.g. `f"{label}  —  {detail}"`) since there's no separate description slot in the base API, or shown via `questionary.Style` mid-line dimming. Actively maintained, this is literally "PyInquirer but not abandoned." Cancel-on-Ctrl-C returns `None` by default, matching today's `select_choice() -> str | None` contract closely. |
| `InquirerPy` | Good fit, more surface area | Same Inquirer.js lineage, more customization/fuzzy-search options than we need. Slightly heavier API for a need this narrow. |
| `simple-term-menu` | Good fit, smallest footprint | Minimal, curses-based, no `prompt_toolkit` dependency at all. Downside: curses doesn't work on native Windows without an extra shim (`windows-curses`) — worth checking whether this project needs Windows CLI support before picking this one. |
| Hand-rolled (`click` + raw ANSI) | No new dependency | Doable given the narrow need (numbered list, read a digit, no arrow-key nav) — zero dependency win, but loses arrow-key navigation UX users may already expect from the current Textual picker, and reinvents cancel/escape handling. |

**Recommendation: `questionary`.** Best balance of "actually lighter than Textual" and "keeps the arrow-key-driven UX users already have," with no platform caveat like `simple-term-menu`'s curses/Windows story, and no reinvention like the hand-rolled option.

## If/when this gets implemented
- Swap `textual` for `questionary` in `pyproject.toml`'s dependencies.
- Rewrite `provider_tui.py`: keep the `SelectionChoice` dataclass and the `select_choice(title, choices) -> str | None` signature so **none of the 6 call sites in `cli.py` need to change** — only the implementation behind that one function changes. `select_choice` becomes a thin sync wrapper around `questionary.select(title, choices=[questionary.Choice(f"{c.label} — {c.detail}" if c.detail else c.label, value=c.key) for c in choices]).ask()`.
- Since `questionary`'s `.ask()` is synchronous (not `async`), check whether `select_choice`'s callers currently `await` it for a real reason (event-loop concurrency) or just because Textual required an async entry point — if the latter, `select_choice` can drop `async` entirely, simplifying every call site slightly instead of requiring a change.
- Verification: run the two Textual-backed wizards manually (`provider add` interactively without flags, and whatever entry point hits `run_first_crawl_wizard`) to confirm the picker still renders, arrow-keys/enter/escape still work, and the detail line still shows.
- No test changes expected beyond whatever currently mocks/exercises `select_choice`/`provider_tui.py` (check for existing tests there first — none were found during this investigation, so this may need a first unit test rather than an update).

## Not doing right now
This plan is the requested research + recommendation. Actually swapping the dependency and rewriting `provider_tui.py` is a separate go-ahead — flagging the concrete plan above so it's ready to execute without re-researching, not assuming approval to start.
