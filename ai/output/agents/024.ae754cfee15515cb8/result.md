No copilot icon either. Confirmed important gap. Now I have everything needed for the report.

## Findings

### 1. `fontawesomefree` dependency status — NOT installed, NOT a listed dependency

- `pyproject.toml` (`/home/user/git/luckydonald/ai-usage/pyproject.toml:9-27`) dependency list has no `fontawesomefree` entry.
- `uv.lock` grep for `fontawesome` — no match.
- `.venv` has no `fontawesomefree` dir; `uv run python -c "import fontawesomefree"` → `ModuleNotFoundError`.
- I pip-downloaded the wheel to my scratchpad (network is available) purely to inspect layout — did not install into the project venv. Only one version is on PyPI: **6.6.0** (release 2024-07-16); older versions exist (6.5.1 … back to 5.13.1) but 6.6.0 is latest/current.

**On-disk layout inside `fontawesomefree-6.6.0-py3-none-any.whl`** (confirmed via `unzip -l`):
```
fontawesomefree/__init__.py                     (empty)
fontawesomefree/static/fontawesomefree/svgs/brands/*.svg    <- 984 files, canonical location
fontawesomefree/static/fontawesomefree/svgs/solid/*.svg
fontawesomefree/static/fontawesomefree/svgs/regular/*.svg
fontawesomefree/static/fontawesomefree/js-packages/@fortawesome/fontawesome-free/svgs/brands/*.svg  <- duplicate copy, same files, nested under js-packages
```
So the package root that `import fontawesomefree; Path(fontawesomefree.__file__).parent` gives you is `fontawesomefree/`, and the icon dir you want is:
`<package_dir>/static/fontawesomefree/svgs/brands/{icon}.svg` (use this one, not the `js-packages/...` duplicate — same content, shorter path, matches Django-static-app convention this package is built for).

- `github.svg` exists at that path (1595 bytes). Confirmed.
- **`claude.svg` does NOT exist. `openai.svg` does NOT exist. No `copilot.svg` either** (checked `brands/` for `claude`, `openai`, `codex`, `copilot`, `microsoft`, `google*`, `github*` — only `github`, `github-alt`, `google*`, `microsoft` exist). Font Awesome Free's brand icon set as of 6.6.0 has never shipped Claude/OpenAI/Copilot brand marks (these are newer or trademark-restricted and were never added to the free tier). **This directly conflicts with the plan note in `ai/query.md:1516`** ("claude, copilot, ~~codex~~ openai") — flag to the user before building the endpoint: those specific icons won't resolve from this package and will 404. They'll need a fallback/local-asset story for those three.
- Version string for the URL: read from `fontawesomefree.dist-info/METADATA` (`Version: 6.6.0`) or via `importlib.metadata.version("fontawesomefree")` at runtime — don't hardcode.

### 2. Source of the requirement — `ai/query.md`

Found the exact spec the user wrote earlier, at `/home/user/git/luckydonald/ai-usage/ai/query.md:1515-1520`:
```
- I want to use the brand icons from the pip package `fontawesomefree` (claude, copilot, ~~codex~~ openai, …)
  - for that create an endpoint serving them at `/img/icons/fontawesomefree/v{package-version}/brands/{icon}.svg`.
  - that route shall be cached, they don't update
  - also for easy frontend embedding provide `/img/icons/fontawesomefree/latest/brands/{icon}.svg` as redirect to that version, however as a 1-day cached redirect.
  - create a svg embed `<Icon source="frontawesomefree" family="brand" version="latest" icon="claude">`, where the params except `icon` already have those defaults.
  - if easier for routing with static file dir, `/api/img/…` would be possible, too.
```

### 3. `src/ai_usage/api.py` — full read, app assembly

File: `/home/user/git/luckydonald/ai-usage/src/ai_usage/api.py` (332 lines total, read in full).

- **No `APIRouter` usage anywhere** in this file or elsewhere in `src/ai_usage/*.py` (grep confirmed zero hits for `APIRouter`/`include_router`). This project is small and idiomatically declares every route with `@app.get(...)` decorators directly inside `create_app()` (lines 94-235), closing over the local `state`/`paths` variables. So the idiomatic way to add a new endpoint here is another `@app.get(...)` (or `@app.mount(...)`) defined inline inside `create_app`, in the same style as the existing handlers — not a separate router module.
- Existing routes for reference (all inside `create_app`, `api.py:72-237`):
  - `GET /api/v1/health` (94)
  - `GET /api/v1/catalog` (99)
  - `GET /api/v1/latest` (121)
  - `GET /api/v1/series` (142)
  - `GET /api/v1/notes` (168)
  - `GET /api/v1/events` (SSE stream, 183)
  - conditionally `GET /api/v1/sentry/sample-error` (210-215, gated on `SENTRY_ENABLE_SAMPLE_ROUTES` env var)
  - **The mount block you asked about** (217-236):
    ```python
    if paths.frontend.exists():
        assets = paths.frontend / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")
        # end if

        @app.get("/{path:path}", include_in_schema=False)
        async def frontend(path: str) -> FileResponse:
            candidate = paths.frontend / path
            if path and candidate.is_file() and paths.frontend in candidate.resolve().parents:
                return FileResponse(candidate)
            return FileResponse(paths.frontend / "index.html")
    else:
        @app.get("/", include_in_schema=False)
        async def placeholder() -> JSONResponse:
            return JSONResponse({"name": "AI Usage", "dashboard": "not built"})
    ```
    Yes — the `/assets` mount is **conditional**: it only registers when `paths.frontend` (the built Vue dist dir, resolved in `settings.py:26-28`) exists on disk *and* an `assets/` subdirectory exists inside it. If the frontend isn't built (dev/test scenarios), neither `/assets` mount nor the SPA-fallback catch-all route exist — instead a JSON placeholder is served at `/`.
  - **Important gotcha for your new route**: the catch-all `@app.get("/{path:path}")` at line 223 only exists when `paths.frontend.exists()`, but it will greedily match *any* unmatched path (e.g. `/img/icons/...` or `/api/img/...`) and try to serve it as an SPA file/fallback to `index.html` — since it's the last route registered in the file, and FastAPI/Starlette matches by registration order, your new icon route **must be declared before** this catch-all block (i.e., insert it above line 217, alongside the other `@app.get("/api/v1/...")` handlers) or it will be shadowed and never reached. If you use the `/img/icons/...` (non-`/api/`) prefix suggested in the query note, same ordering rule applies since that catch-all matches everything.

### 4. Caching header patterns — none exist yet

- Grepped `src/ai_usage/*.py` for `Cache-Control`, `max-age`, `immutable`, `RedirectResponse`, `FileResponse`: only hits are the two `FileResponse(...)` calls already shown above (lines 227, 229) — no headers set on them, no `Cache-Control` anywhere in the codebase, no `RedirectResponse` import/usage anywhere.
- So there's no existing pattern to mirror — you'll be introducing this from scratch. Practically:
  - For the version-pinned "cache forever" SVG response, import `from fastapi.responses import FileResponse` (already imported at `api.py:16`) and pass `headers={"Cache-Control": "public, max-age=31536000, immutable"}` to `FileResponse(path, media_type="image/svg+xml", headers={...})`.
  - For the `.../latest/...` redirect, import `RedirectResponse` from `fastapi.responses` (not yet imported — add to the existing import line 16) and return `RedirectResponse(url=..., status_code=307/308, headers={"Cache-Control": "public, max-age=86400"})` for the ~1-day cache.

### 5. `pyproject.toml` — dependencies and Python version

Full dependency list (`pyproject.toml:9-27`): `aiosqlite`, `alembic`, `click`, `cryptography`, `curl-cffi`, `fastapi`, `fastscheduler`, `httpx`, `pexpect` (non-Windows), `platformdirs`, `pydantic`, `pyyaml`, `sentry-sdk[fastapi]`, `sqlalchemy[asyncio]`, `textual`, `typer`, `uvicorn`. Optional groups: `browser` (browser-cookie3, playwright, pygobject, pywebview) and `test` (hypothesis, pytest, pytest-asyncio, pytest-cov, respx).

- **No existing SVG/static-asset/icon dependency** anywhere — you'd be adding `fontawesomefree` fresh.
- **Python version constraint: `requires-python = ">=3.14"`** (`pyproject.toml:8`), confirmed by `python3 --version` / `uv run python --version` → `Python 3.14.6`. `[tool.ruff] target-version = "py314"` and `[tool.pyright] pythonVersion = "3.14"` reinforce this. So you're free to use the newest `pathlib` API (e.g. `Path.walk()`, match statements, `X | Y` unions everywhere — already used throughout, e.g. `uvicorn.Server | None` at `api.py:53`) without any back-compat concerns.

### Summary of things to flag before implementation

1. `fontawesomefree` must be added to `pyproject.toml` `dependencies` (not installed currently).
2. **Claude, OpenAI, and Copilot brand icons do not exist in fontawesomefree 6.6.0** (only version on PyPI) — the plan's `<Icon icon="claude">` example will 404 against this package. Needs a decision: fallback/local override assets, or accept 404s, or pick different icon set for those three.
3. Use `svgs/brands/*.svg` under `<pkg>/static/fontawesomefree/` (not the duplicated `js-packages/...` copy) as the canonical source path.
4. New route(s) must be inserted before the `paths.frontend.exists()` catch-all block at `api.py:217-236`, since that block's `@app.get("/{path:path}")` will shadow anything declared after it.
5. No `RedirectResponse` import currently exists in `api.py` — needs adding to the line-16 import statement.
6. No existing caching-header convention in the codebase to copy — you'll set `headers={"Cache-Control": ...}` directly on `FileResponse`/`RedirectResponse` per the two cache profiles (immutable long-lived for the pinned version, ~1 day for the `latest` redirect).