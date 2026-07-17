import base64
import os
from datetime import UTC, datetime

import httpx
import pytest

from ai_usage.api import create_app, exposed_host
from ai_usage.models import Metric, ProviderFetchResult, Usage
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


def test_exposure_detection() -> None:
    assert exposed_host("0.0.0.0") is True
    assert exposed_host("localhost") is False
# end def

