"""Shared plumbing for real-browser (Playwright) end-to-end tests.

These tests drive the actually-built frontend (real echarts, real DOM, real
`localStorage`) inside a real Chromium tab, talking to a real backend on a real TCP
socket — the kind of bug a fully-mocked unit test structurally cannot catch (wrong
echarts API finder shape, `localStorage` round-tripping, etc.).
"""

import asyncio
import contextlib
import socket
from pathlib import Path

import pytest
import uvicorn

from ai_usage.api import create_app

playwright_async_api = pytest.importorskip("playwright.async_api")

FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"


def skip_unless_frontend_built() -> None:
    if not (FRONTEND_DIST / "index.html").exists():
        pytest.skip("frontend/dist not built; run `corepack yarn@4.9.2 build` first")
    # end if
# end def


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]
    # end with
# end def


@contextlib.asynccontextmanager
async def running_app(paths):
    app = create_app(paths)
    port = free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)
    # end while
    try:
        yield app.state.runtime, f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task
        await app.state.runtime.close()
    # end try
# end def
