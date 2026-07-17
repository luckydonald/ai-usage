import base64
import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from ai_usage.database import Database
from ai_usage.history import HistoryStore
from ai_usage.models import Metric, ProviderFetchResult, Usage
from ai_usage.orm import MetricSampleRecord
from ai_usage.settings import Paths


def temporary_paths(root):
    return Paths(
        root=root,
        services=root / "services",
        history=root / "history",
        local=root / "local",
        database=root / "local" / "state.sqlite3",
        credential_key=root / "credential.key",
        logs=root / "local" / "logs",
        frontend=root / "frontend",
    )
# end def


@pytest.mark.asyncio
async def test_credentials_are_encrypted_and_round_trip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AI_USAGE_CREDENTIAL_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    paths = temporary_paths(tmp_path)
    paths.ensure()
    database = Database(paths)
    await database.migrate()
    credential_id = await database.put_credential("codex", "Personal", {"token": "secret"})
    assert await database.get_credential(credential_id) == {"token": "secret"}
    assert b"secret" not in paths.database.read_bytes()
    assert paths.database.stat().st_mode & 0o777 == 0o600
    await database.close()
# end def


@pytest.mark.asyncio
async def test_history_is_idempotently_indexed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AI_USAGE_CREDENTIAL_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    paths = temporary_paths(tmp_path)
    paths.ensure()
    database = Database(paths)
    await database.migrate()
    history = HistoryStore(paths, database)
    now = datetime.now(UTC)
    result = ProviderFetchResult(
        service="codex",
        provider="app-server",
        account_id="account",
        fetched_at=now,
        metrics=[
            Metric(
                key="five-hours",
                name="Five hours",
                usage=Usage(percentage=25),
                observed_at=now,
            )
        ],
    )
    events = await history.append_result(result)
    await history.index_file(history.event_path(events[0]))
    async with database.sessions() as session:
        count = await session.scalar(select(func.count()).select_from(MetricSampleRecord))
    # end with
    assert count == 1
    await database.close()
# end def
