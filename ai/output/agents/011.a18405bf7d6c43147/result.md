Plan mode wasn't actually active on my end (tool says I'm not in it), so here's the plan directly — six parts, each independently committable:

1. **Git auto-commit as real setting** — add `git-backup-enable/disable/status` CLI commands + `ConfigStore` setter; currently `git.enabled` is read but never written anywhere.
2. **`--help` grouping** — Typer 0.27 (installed) supports `rich_help_panel`; group into Provider management / Operate / Setup / **Internal tooling** (last: `ingest-claude`, `claude-relay-install`, `claude-relay-remove`).
3. **Graph fixes** — auto-drop series to 0% once a window's `end` passes (even outside selected range); add `"custom"` range preset with two date inputs, end-date inclusive (end-of-day).
4. **Frontend rebuild** — strip cards/current layout, keep data plumbing (fetchCatalog/fetchSeries/live EventSource), restyle with your 5 semantic colors (primary/secondary/misc/success/error), respecting the success+misc-clash constraint. Biggest, most subjective part — doing last.
5. **Brand color generator** — replace `graph.py`'s hash-into-shared-palette with per-service base colors (codex `#99bd3c` scale, claude `#DE7356`, gemini/perplexity/cursor mapped for later), deterministic per-account variant within a brand's family.
6. **Completion staleness check** — hash the rendered completion script, compare against installed file, registry `hash → version` in a packaged JSON, reuses existing `interactive_terminal()` isatty pattern for the 5-way prompt (yes once/always, no once/this-version/never), wired into `main_callback` so it runs on every command. Includes the test you asked for (current hash present in registry).

Flagged for you before I touch it:
- **Claude/Codex 403** — providers built last session now 403. Almost certainly expired browser cookies, not a code bug. Want to do a fresh live-browser session to confirm/re-capture, or should I look at something else first?
- **Completion registry value type** — you said `dict[str, int]` hash→version, but version is semver string (`"0.1.0"`) not int. Want a literal int schema-version counter instead, or is string fine and "int" was just loose phrasing?

Want me to start with parts 1/2/6 (backend, low-risk, independent), or something else first?