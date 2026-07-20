import base64
import os
import socket
from datetime import UTC, datetime

import httpx
import pytest

from ai_usage.api import DEFAULT_PORT, create_app, exposed_host, resolve_port
from ai_usage.models import Metric, ProviderFetchResult, Usage
from ai_usage.notes import NotesStore
from tests.test_storage import temporary_paths


@pytest.mark.asyncio
async def test_api_catalog_latest_and_series(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AI_USAGE_CREDENTIAL_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    paths = temporary_paths(tmp_path)
    app = create_app(paths)
    runtime = app.state.runtime
    await runtime.initialize()
    now = datetime.now(UTC)
    await runtime.history.append_result(
        ProviderFetchResult(
            service="claude",
            provider="statusline",
            account_id="account",
            fetched_at=now,
            metrics=[
                Metric(
                    key="five-hours",
                    name="Five hours",
                    usage=Usage(percentage=42),
                    observed_at=now,
                )
            ],
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/api/v1/health")
        catalog = await client.get("/api/v1/catalog")
        latest = await client.get("/api/v1/latest")
        series = await client.get(
            "/api/v1/series",
            params={"start": "2026-01-01T00:00:00Z", "end": "2027-01-01T00:00:00Z"},
        )
    # end with
    assert health.json() == {"status": "ok"}
    assert catalog.json()["metrics"][0]["metric_key"] == "five-hours"
    assert latest.json()[0]["percentage"] == 42
    assert series.json()[0]["points"][0]["percentage"] == 42
    await runtime.close()
# end def


@pytest.mark.asyncio
async def test_api_notes_reports_open_and_closed_ranges(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AI_USAGE_CREDENTIAL_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    paths = temporary_paths(tmp_path)
    app = create_app(paths)
    runtime = app.state.runtime
    await runtime.initialize()
    store = NotesStore(paths)
    started = datetime(2026, 7, 1, tzinfo=UTC)
    ended = datetime(2026, 7, 10, tzinfo=UTC)
    store.diff_and_record("claude", "account", ["+50% weekly limits promo"], set(), started)
    store.diff_and_record("claude", "account", [], {"+50% weekly limits promo"}, ended)
    store.diff_and_record("codex", "other-account", ["3 resets available"], set(), started)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/notes")
    # end with
    ranges = {(item["service"], item["account_id"], item["text"]): item for item in response.json()}
    closed = ranges[("claude", "account", "+50% weekly limits promo")]
    open_range = ranges[("codex", "other-account", "3 resets available")]
    assert closed["end"] is not None
    assert open_range["end"] is None
    await runtime.close()
# end def


def test_exposure_detection() -> None:
    assert exposed_host("0.0.0.0") is True
    assert exposed_host("localhost") is False
# end def


def test_resolve_port_keeps_explicit_port_even_if_occupied() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
        blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        occupied_port = blocker.getsockname()[1]
        assert resolve_port("127.0.0.1", occupied_port, explicit=True) == occupied_port
    # end with
# end def


def test_resolve_port_falls_back_when_default_is_occupied(monkeypatch) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
        blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        test_default = blocker.getsockname()[1]
        monkeypatch.setattr("ai_usage.api.DEFAULT_PORT", test_default)
        resolved = resolve_port("127.0.0.1", test_default, explicit=False)
        assert resolved != test_default
    # end with
# end def


def test_resolve_port_keeps_default_when_free(monkeypatch) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]
    # end with
    monkeypatch.setattr("ai_usage.api.DEFAULT_PORT", free_port)
    assert resolve_port("127.0.0.1", free_port, explicit=False) == free_port
# end def


@pytest.mark.asyncio
async def test_sse_stream_stops_once_shutdown_is_signalled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AI_USAGE_CREDENTIAL_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    paths = temporary_paths(tmp_path)
    app = create_app(paths)
    runtime = app.state.runtime
    await runtime.initialize()
    runtime.shutdown_event.set()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream("GET", "/api/v1/events") as response:
            chunks = [chunk async for chunk in response.aiter_text()]
        # end async with
    # end async with
    assert chunks == []
    await runtime.close()
# end def

