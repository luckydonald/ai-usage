import base64
import os
from datetime import UTC, datetime
from typing import Any

import pytest

from ai_usage.collector import Collector
from ai_usage.config import ConfigStore
from ai_usage.crawler import Crawler
from ai_usage.database import Database
from ai_usage.history import HistoryStore
from ai_usage.models import AccountConfig, Metric, ProviderFetchResult, Usage
from ai_usage.providers import Provider, ProviderRegistry
from tests.test_storage import temporary_paths


class ChangingProvider(Provider):
    service = "test-service"
    key = "changing"
    display_name = "Changing test provider"

    def __init__(self) -> None:
        self.percentage = 3.0
    # end def

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        del credential
        now = datetime.now(UTC)
        return ProviderFetchResult(
            service=self.service,
            provider=self.key,
            account_id=account.id,
            fetched_at=now,
            metrics=[
                Metric(
                    key="five-hours",
                    name="5-hour window",
                    usage=Usage(percentage=self.percentage),
                    observed_at=now,
                )
            ],
        )
    # end def
# end class


@pytest.mark.asyncio
async def test_fetch_and_crawl_report_progress(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AI_USAGE_CREDENTIAL_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    paths = temporary_paths(tmp_path)
    paths.ensure()
    database = Database(paths)
    await database.migrate()
    history = HistoryStore(paths, database)
    config = ConfigStore(paths)
    account = AccountConfig(
        id="account",
        service="test-service",
        provider="changing",
        name="Test account",
    )
    provider = ChangingProvider()
    registry = ProviderRegistry()
    registry.register(provider)
    messages: list[str] = []
    collector = Collector(config, database, history, registry, reporter=messages.append)

    first = await collector.fetch_account(account)
    provider.percentage = 99
    second = await collector.fetch_account(account, operation="crawling")

    assert any(message.startswith("Started fetching Test account") for message in messages)
    assert any("no previous value -> 3%" in message for message in messages)
    assert any("3% -> 99%" in message for message in messages)
    assert any(message.startswith("Done crawling Test account") for message in messages)

    crawler = Crawler(collector, config, database, reporter=messages.append)
    await crawler.ensure_states([account])
    now = datetime.now(UTC)
    await crawler.update_state(account, first, now)
    await crawler.update_state(account, second, now)

    assert "Test account: decreasing crawl interval to 60 seconds after usage increased." in messages
    assert "Test account: next crawl in approximately 60 seconds." in messages
    await database.close()
# end def
