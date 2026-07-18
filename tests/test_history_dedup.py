import base64
import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from ai_usage.database import Database
from ai_usage.history import HistoryStore
from ai_usage.models import Metric, ProviderFetchResult, Usage
from ai_usage.orm import MetricSampleRecord
from tests.test_storage import temporary_paths


async def _append(history: HistoryStore, observed_at: datetime, percentage: float) -> None:
    await history.append_result(
        ProviderFetchResult(
            service="codex",
            provider="app-server",
            account_id="account",
            fetched_at=observed_at,
            metrics=[
                Metric(
                    key="five-hours",
                    name="Five hours",
                    usage=Usage(percentage=percentage),
                    observed_at=observed_at,
                )
            ],
        )
    )
# end def


@pytest.mark.asyncio
async def test_dedup_keeps_first_and_last_of_an_old_duplicate_run(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AI_USAGE_CREDENTIAL_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    paths = temporary_paths(tmp_path)
    paths.ensure()
    database = Database(paths)
    await database.migrate()
    history = HistoryStore(paths, database)

    base = datetime.now(UTC) - timedelta(days=10)
    for hour in range(5):
        await _append(history, base + timedelta(hours=hour), 50.0)
    # end for
    await _append(history, base + timedelta(hours=5), 60.0)

    summary = await history.dedup(older_than_days=7)

    assert summary["removed_lines"] == 3
    assert summary["touched_files"] == 1

    async with database.sessions() as session:
        count = await session.scalar(select(func.count()).select_from(MetricSampleRecord))
    # end with
    assert count == 3
    await database.close()
# end def


@pytest.mark.asyncio
async def test_dedup_leaves_recent_duplicates_alone(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AI_USAGE_CREDENTIAL_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    paths = temporary_paths(tmp_path)
    paths.ensure()
    database = Database(paths)
    await database.migrate()
    history = HistoryStore(paths, database)

    now = datetime.now(UTC)
    for minute in range(5):
        await _append(history, now - timedelta(minutes=minute), 50.0)
    # end for

    summary = await history.dedup(older_than_days=7)

    assert summary == {"removed_lines": 0, "touched_files": 0}
    async with database.sessions() as session:
        count = await session.scalar(select(func.count()).select_from(MetricSampleRecord))
    # end with
    assert count == 5
    await database.close()
# end def
