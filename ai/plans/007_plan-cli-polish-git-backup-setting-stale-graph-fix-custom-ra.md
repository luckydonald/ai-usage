# Plan: CLI polish, git-backup setting, stale-graph fix, custom range, brand color system, completion staleness check

Scope is nine independent items from the user's `/plan` prompt. Grouped into 6 parts; each part is separately committable (per lplp style — commit after each completed task).

## Part 0 — Claude/Codex web 403 (deferred, not actionable right now)

`ClaudeWebUsageProvider`/`CodexWebUsageProvider` (added last session) now return 403. Root cause is almost certainly stale/expired browser cookies captured during the last live-browser session (Claude session cookies rotate; Codex's `accessToken` mint step depends on a live `chatgpt.com` session too) — not a code bug. This needs a fresh live-browser debugging pass (same as last time: user logs in, agent inspects via `claude-in-chrome`), which is out of scope for this coding plan. **Options to discuss with user before doing any code work here:**
1. Re-run the same live-browser capture session to confirm cookies just expired (most likely) — no code change needed, just re-verify.
2. If it's not just expired cookies (e.g. Claude added a required header/CSRF token, or Codex's session endpoint response shape changed), inspect the new 403 response body/headers live and patch the provider.
3. Longer-term: add a credential-refresh/expiry story (e.g. surface a clear "credential expired, re-run `provider add`" error) instead of a raw 403 — separate follow-up, not blocking.

Not implementing anything for this item in this plan — flagging it as the first thing to do interactively once this plan is approved, before or after the rest.

## Part 1 — Git auto-commit as a real, shared setting

Today `git_backup_enabled()` (`src/ai_usage/git_backup.py:18`) reads `config.global_config().get("git", {}).get("enabled")` but nothing ever writes that key — it's a dead setting, only reachable by hand-editing the global YAML.

- Add `ConfigStore.set_global_git_enabled(enabled: bool) -> None` in `src/ai_usage/config.py`, mirroring how `global_config()` reads/writes the shared global YAML (check `ConfigStore`'s existing save mechanism for the global file — reuse it, don't invent a new one).
- Add a CLI command `ai-usage git-backup enable` / `ai-usage git-backup disable` (a small `git_backup_app` sub-typer, or two flat commands `git-backup-enable`/`git-backup-disable` — match existing naming convention, e.g. `history-cleanup`, `db-upgrade` use flat kebab names, so prefer flat `git-backup-enable`/`git-backup-disable` for consistency) that calls the new setter and prints current state.
- Add `ai-usage git-backup status` (or fold into the two commands' output) showing whether it's currently on/off.
- Test: round-trip enable → `global_config()` reflects it → `git_backup_enabled()` returns True; same for disable.

## Part 2 — `--help` grouping and internal-tooling section

Typer 0.27 (confirmed installed version) supports `rich_help_panel="..."` per `@app.command(...)`. Group `src/ai_usage/cli.py`'s top-level commands:

- **Provider management** panel: the whole `provider_app` sub-typer (`add`, `discover`, `list`, `status`, `remove`, `rename`, `merge`, `hosts add/remove`) — already grouped by being a subcommand, but confirm its own `--help` groups host-related ones vs core ones if useful (likely fine as-is).
- **Operate** panel (or similar): `fetch`, `crawl`, `up`, `serve`, `history-cleanup`, `db-upgrade`.
- **Setup** panel: `install`, `uninstall`, `completion`, plus the new `git-backup-*` commands from Part 1.
- **Internal tooling** panel (last section, per explicit request): `ingest-claude`, `claude-relay-install`, `claude-relay-remove` — these are internal plumbing invoked by the relay script itself, not meant for direct user use day-to-day.

Implementation: add `rich_help_panel="Internal tooling"` (etc.) to each `@app.command(...)` decorator at `cli.py:1067,1107,1141,1151,1161,1171,1183,1205,1213,1229,1251,1296` (exact panel assignment per command above). No behavior change — purely `--help` output cosmetics. Verify with `ai-usage --help` that panels render in the intended order (Typer/Rich renders panels in first-registration order, so the internal-tooling commands' decorators may need reordering in the source, or Typer may support an explicit panel order — check during implementation and reorder command definitions if needed so "Internal tooling" prints last).

## Part 3 — Graph: window-end auto-drop to 0%, and custom date range

**Auto-drop to 0% after window end** (`frontend/src/chart.ts`): currently a series' line just stops at its last real point; if the metric's reset/window end passes while the user's selected range extends past it, the line doesn't visually go to 0. Add a synthetic trailing point: for each `item.windows` entry with an `end` in the past (relative to `options.now`/chart "now"), extend `rendered` data for the `/actual` series (or add a small dedicated segment, consistent with the existing per-window segment pattern already used for reset-line/projection/exhausted) with a point `[window.end, 0]` immediately after that window ends, so the rendered line visibly drops to 0% right at the window boundary — even when `window.end` falls outside `options.start`/`options.end` (i.e. compute this before/independent of the axis clipping, since ECharts will just clip the out-of-range portion, which is fine and matches "shall go to 0% automatically, even if the window end is not part of the current selected range"). Add a `chart.test.ts` case asserting the trailing zero point appears once a window's `end` is in the past.

**Custom range** (`frontend/src/time.ts` + `App.vue`): add `"custom"` to `TimePreset`; `rangeForPreset` needs an overload/second parameter path for custom start/end (custom dates won't come from `rangeForPreset` at all — they'll be plain `ref<Date>` state set by two date-picker inputs). In `App.vue`:
- Add `<input type="date">` × 2 (start/end) shown only when `preset === "custom"`, wired into `filters`-adjacent refs (e.g. `customStart`/`customEnd`).
- "Both dates included" means the end date's input value (a day, no time) must be treated as the *end of that day* (23:59:59.999) when building the query range, not midnight-start — otherwise the last day would be excluded. Convert `customEnd`'s date-only value to end-of-day before passing to `fetchSeries`.
- `load()` branches: if `preset === "custom"`, use `[customStart, customEnd]` instead of calling `rangeForPreset`.
- Test: `time.test.ts` — add a case building the end-of-day boundary from a plain `YYYY-MM-DD` string.

## Part 4 — Frontend rebuild: strip everything but graphs, apply new brand palette

User: *"Remove everything except the graphs and build the website from scratch."* Interpreting scope: drop the "Latest usage" cards section (`App.vue:101-107`), the exposed-without-auth banner, and the current ad hoc filter-sidebar layout/styling — keep the underlying data flow (`fetchCatalog`/`fetchSeries`/`fetchLatest`, `EventSource` live updates, filters state, theme toggle) since none of that was called out as unwanted, only the *visual result* ("build the website from scratch" reads as a redesign, not a re-architecture — confirm with user before deleting the exposed-warning banner specifically, since that's a security-relevant notice, not decoration).

New semantic color roles (from the user's table), defined once as CSS custom properties in `frontend/src/styles/main.scss`:

| role | hex | on-color text |
|---|---|---|
| `--color-primary` | `#6C0DE9` | white |
| `--color-secondary` | `#00C0DE` | black |
| `--color-misc` | `#FFC0DE` | black |
| `--color-success` | `#69F69F` | black |
| `--color-error` | `#FF6969` | white |

Constraint to respect while restyling: primary works atop every other color (safe for overlays/accents on any surface); success and misc are both very bright and must never sit directly adjacent/on top of each other (e.g. don't use one as a badge background on the other's card) — every other pairing is fine.

Rebuild `App.vue` template/layout and `main.scss` using only these roles for chrome (buttons, active-filter highlighting, error banner → `--color-error`, success/live-indicator → `--color-success`, misc badges/tags → `--color-misc`), keeping dark/light mode support (`.dark` class already exists — recompute on-color text per mode if a role's background needs to invert, though the roles above already specify fixed hex, so likely no per-theme variant is needed for the *brand* colors themselves, only for surrounding chrome/background/text).

This is the largest, most subjective part — recommend doing it last and pairing with a quick manual look (dev server + `run` skill / screenshot) before calling it done, since "build from scratch" is a design judgment call, not a mechanical change.

## Part 5 — Per-provider brand-based series color generator

Replace `src/ai_usage/graph.py`'s `generated_color()` (currently: SHA-256 hash of `service/provider/account_id/metric_key` → index into one shared 8-color `PALETTE`, so different services' series colors are unrelated to each other) with a **per-service base color + distinguishable-variant** scheme:

- New mapping `SERVICE_BASE_COLORS: dict[str, str]` (or a small `tuple[str, ...]` per service to match the "full scale" palettes the user gave):
  - `codex`: base `#99bd3c`, full scale `("#ee5091", "#199fd7", "#99bd3c", "#fc7942", "#8a50d8")` (only `#99bd3c` used for now, but store the full scale so multi-account variation has somewhere to pull from later)
  - `claude`: base `#DE7356` (no fuller scale given — single color, variants derived algorithmically, see below)
  - `perplexity` (not yet a provider — add color mapping only, no provider code): `#21808D`
  - `gemini` (not yet a provider): base `#9177C7`, scale `("#4796E3", "#9177C7", "#CA6673")`
  - `cursor` (not yet a provider) — **must always be displayed/labelled as "Cursor AI" or "Cursor Code" everywhere user-facing, never bare "Cursor"** (trademark note from user, EU-non-trademarkable reasoning aside, this is a hard labeling rule for any future cursor work — record as a memory too, not just in this plan, since it'll matter again whenever a Cursor provider is actually built): base `#72716D`, scale `("#43413C", "#55544F", "#72716D", "#D6D5D2", "#FFFFFF")`.
- New function, replacing `generated_color`: `def brand_color(service: str, identity: str) -> str` — look up `service`'s scale (fall back to the existing hash-into-shared-`PALETTE` behavior for any unknown/future service not yet in the mapping, so nothing crashes/breaks for unmapped services); if the service has a multi-color scale, hash `identity` (still `account_id/metric_key`, i.e. everything except `service`+`provider` since same-brand accounts should share the *family*, just pick a distinguishable member) into that scale's colors; if only a single base color is defined (e.g. Claude, Perplexity — no scale given), derive 2-3 lightness/saturation variants algorithmically (HSL lightness jitter, deterministic per identity hash) rather than reusing one flat color for every Claude account, since the ask is "distinguishable" per account even within one brand.
- Update `build_series()` (`graph.py:66`) to call `brand_color(service, "/".join((account_id, metric_key)))` instead of `generated_color("/".join(identity))`.
- Tests in `tests/test_graph.py` (or wherever graph tests live — check existing file name): assert two different codex accounts get two different colors both drawn from the codex scale; assert an unknown service still gets a deterministic fallback color (no crash); assert same account+metric always returns the same color (determinism preserved, same guarantee `generated_color` had).

## Part 6 — Shell completion staleness check + versioned hash registry

Research confirmed (fork report, see below) the current mechanism:
- `src/ai_usage/shell_completion.py` renders via Click's `get_completion_class(shell).source()` and writes to `paths.root / "completions" / f"ai-usage.{shell}"` (bash/zsh) or `~/.config/fish/completions/ai-usage.fish` — no existing hash/versioning at all.
- `sys.stdin.isatty()`/`sys.stdout.isatty()` interactive-session pattern already exists: `interactive_terminal(no_input)` at `cli.py:264`, reused for other yes/no prompts — reuse this exact helper for the completion-staleness prompt, don't reinvent.
- CLI version lives in `pyproject.toml:7` (`version = "0.1.0"`) and `src/ai_usage/__init__.py:3` (`__version__ = "0.1.0"`) — use `__version__` as the source of truth for the hash↔version registry (avoid re-parsing `pyproject.toml` at runtime).

Design:
1. **Content hash of the completion script**: `hashlib.sha256(render_script(main, shell).encode()).hexdigest()` — hashing the *rendered script content* is simplest and directly detects "does the installed file match what we'd generate right now," which is exactly the staleness signal needed (no need to separately hash "the input"/command tree — the rendered script *is* a deterministic function of the command tree, so hashing its output covers it).
2. **Registry file**: a new `hash_versions.json` (or similar) bundled as package data (not per-user — it's a mapping the *package* ships, recording which past `__version__`s produced which script hash), shape `dict[str, str]` — hash → version string (user asked for `dict[str, int]` "hash to version" but versions here are strings like `"0.1.0"`, not ints; flag this to the user as a wording mismatch to confirm — likely they meant "a dict, so it's less confusing" generically, and the *value* should just be whatever the version type actually is. Confirm before implementing if `int` was meant literally, e.g. a separate incrementing schema-version counter unrelated to the semver `__version__`).
3. **Update-check flow**, wired into the `main_callback` (`cli.py:222`, `invoke_without_command=True`, already runs before every command) or a small helper called from it:
   - If no completion file exists for the detected/last-installed shell → do nothing (per explicit requirement).
   - If completion file exists: compute current hash, compare to file's actual hash (not just look up in registry) — if it matches current render, nothing to do.
   - If mismatched: look up file's hash in the registry to report *which old version* installed it (best-effort — if hash isn't in the registry, still flag staleness, just without a version number).
   - Non-interactive (`interactive_terminal(no_input=False)` false, i.e. not a TTY) → `LOGGER.warning(...)`, continue.
   - Interactive → prompt with the 5 choices (yes-once / yes-always / no-once / no-this-version-never-again / no-never). Persist "always"/"never" decisions somewhere durable (new key in the *local*, non-git config — `paths.local`, matching precedent of other machine-local state like `git_backup_state.json` — e.g. `completion_update_preference.json` with `{"policy": "always" | "never" | "never-below:<version>"}` or similar; "no, not this new version" implies a per-version skip-list, "no, never" implies a blanket flag).
   - On "yes" (once or always), re-run `install_completion(...)` for that shell.
4. Add the current hash to the registry at release time — since this is dev-authored, add an entry for the current `__version__`/current rendered script now, and add the **unit test the user explicitly asked for**: "confirm the current hash is in that dict" — i.e. a test that renders the completion script(s) for the current code, computes the hash, and asserts `__version__`'s hash is present in the registry (this test will fail on every future command-tree change until the registry is updated, which is the intended forcing function).

Files touched: `src/ai_usage/shell_completion.py` (hash/registry helpers), `src/ai_usage/cli.py` (wire the check into `main_callback`, add the interactive prompt), a new packaged JSON/data file for the registry, `tests/test_shell_completion.py` (new or extended).

## Sequencing recommendation

Parts 1–3 and 6 are backend-only, independent, low-risk — good to do first and commit separately. Part 5 (color generator) is backend-only and independent of Part 4. Part 4 (frontend rebuild) is the biggest, most subjective, and benefits from Part 5 already existing (so real brand colors are available while restyling) — do it last. Part 0 is a conversation to have with the user before/alongside the rest, not blocking.

## Todos

- [x] Git autocommit as toggleable global setting
- [ ] Group CLI --help and separate internal tooling
- [ ] Graph: force 0% after window ends
- [ ] Custom date range picker
- [ ] Frontend rebuild: strip to graphs-only + new palette
- [ ] Shell completion staleness detection + versioned hashes
- [ ] Claude/Codex web login via pywebview
