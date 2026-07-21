All confirmed directly by running the package in an isolated venv (not the project venv). Here's the full report.

## 1. Does the package exist?

Yes. **`fontawesome-free-pack`** exists on PyPI exactly as named (no underscore/no-hyphen variants needed — that's the real distribution name).

- Latest version: **7.3.0** (released 2026-07-01)
- Release history: 7.0.0 (2025-09-01) → 7.0.1 (2025-09-04) → 7.1.0 (2025-10-03) → 7.2.0 (2026-02-16) → 7.3.0 (2026-07-01)
- That's 5 releases over ~10 months, roughly one every 1-4 months — actively maintained, tracks Font Awesome's own major version numbering (7.x).
- Upstream project: https://github.com/2bndy5/redist-icons (also published as a Rust crate on crates.io under the same name).

## 2. On-disk layout — important correction to the assumed structure

**There is no `svgs/brands/*.svg` directory at all.** This is not a plain SVG-file redistribution — it's a compiled Rust extension module (built with maturin/PyO3) shipped as a platform wheel. The wheel contains:

```
fontawesome_free_pack/__init__.py
fontawesome_free_pack/__init__.pyi
fontawesome_free_pack/fontawesome_free_pack.abi3.so   (~5 MB compiled binary, all SVGs embedded inside)
fontawesome_free_pack/py.typed
fontawesome_free_pack-7.3.0.dist-info/METADATA, LICENSE, RECORD, sboms/...
```

All SVG strings are compiled into the binary `.so`/Rust code and exposed only through the Python API — there's nothing to glob on disk. Access is via:

```python
from fontawesome_free_pack import get_icon, BRANDS_CLAUDE, BRANDS_OPENAI, BRANDS_MICROSOFT
icon = get_icon("brands/claude")   # slug format: "<family>/<slug>"
icon.svg, icon.slug, icon.family, icon.width, icon.height, icon.label, icon.last_modified
```

Families are `brands`, `solid`, `regular`. There are 566 `BRANDS_*` constants total (confirmed via the `.pyi` stub), plus the equivalent count reachable via `get_icon("brands/<slug>")`.

## 3. Brand icon coverage for AI/tech tools — checked exhaustively

Grepped every `BRANDS_*` constant name in the type stub for "claude", "openai", "copilot", "gpt", "anthropic", "microsoft", "github":

```
BRANDS_CLAUDE          -> present   (get_icon("brands/claude") works, returns valid SVG)
BRANDS_OPENAI          -> present   (get_icon("brands/openai") works, returns valid SVG)
BRANDS_MICROSOFT       -> present   (get_icon("brands/microsoft") works, returns valid SVG)
BRANDS_GITHUB          -> present
BRANDS_GITHUB_ALT      -> present
BRANDS_SQUARE_GITHUB   -> present
```

**No matches at all for "copilot", "gpt", or "anthropic"** — no `BRANDS_COPILOT`, `BRANDS_GITHUB_COPILOT`, `BRANDS_MICROSOFT_COPILOT`, `BRANDS_GPT`, or `BRANDS_ANTHROPIC` exist. I confirmed this both by grepping the stub and by runtime lookup: `get_icon("brands/copilot")` and `get_icon("brands/github-copilot")` both return `None`.

So: **claude.svg equivalent exists, openai.svg equivalent exists, but there is no copilot icon of any kind.** This matches upstream Font Awesome Free itself — FA added `claude`, `openai`, and `microsoft` brand glyphs in recent 6.x/7.x releases but has never shipped a Copilot-specific glyph (Copilot isn't a distinct FA brand icon upstream either, as far as this package reflects).

## 4. License and upstream tracking

- PyPI `License:` field: **`(CC-BY-4.0 AND OFL-1.1 AND MIT)`**
- The shipped `LICENSE` file is the standard Font Awesome Free license bundle: CC BY 4.0 for icons (SVG/JS), SIL OFL 1.1 for fonts, MIT for code — copyright Fonticons, Inc.
- The README explicitly states: *"A redistribution of SVG assets and some metadata from the `@fortawesome/fontawesome-free` npm package."* It optimizes the SVGs with SVGO (strips `width`/`height`, keeps `viewBox`) specifically so they can be injected into HTML easily.
- It does **not** claim to be a "more up-to-date fork" with independent icon additions — it's a straight redistribution/rebuild of whatever the current `@fortawesome/fontawesome-free` npm package version contains, repackaged as a Rust crate + Python binding. Version 7.3.0 corresponds to Font Awesome Free npm package version 7.3.0 (project uses matching version numbers).

## 5. Importable module name

- PyPI distribution name: `fontawesome-free-pack`
- Importable module name: **`fontawesome_free_pack`** (straightforward hyphen→underscore normalization, confirmed by `from fontawesome_free_pack import get_icon`)
- `importlib.metadata.version("fontawesome-free-pack")` is the correct call (metadata/distribution lookups use the PyPI distribution name with hyphens, not the underscored import name) — confirmed this returns `7.3.0` correctly in an isolated venv.

## Key implication for your plan

Since there's no `svgs/brands/*.svg` directory on disk, any implementation plan that assumed "copy files out of `svgs/brands/`" needs to instead call `get_icon("brands/<slug>")` (or use the `BRANDS_*` constants) at runtime/build-time in Python to obtain SVG strings, then write those strings to files yourself if you need standalone `.svg` files. And plan for the fact that there is no Copilot icon available in this package at all — you'll need a substitute source (e.g., simple-icons or a manually sourced SVG) for that one.