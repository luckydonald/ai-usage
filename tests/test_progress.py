import base64
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from ai_usage.collector import Collector
from ai_usage.config import ConfigStore
from ai_usage.crawler import STALE_RECHECK_SECONDS, Crawler
from ai_usage.database import Database
from ai_usage.history import HistoryStore
from ai_usage.models import (
    AccountConfig,
    AccountIdentity,
    FetchStatus,
    Metric,
    ProviderFetchResult,
    SubscriptionStatus,
    Usage,
)
from ai_usage.providers import Provider, ProviderRegistry
from tests.test_storage import temporary_paths


class StaleProvider(Provider):
    service = "test-service"
    key = "stale"
    display_name = "Stale test provider"

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
            status=FetchStatus.STALE,
            error="no new statusline data yet (last update 3600s ago)",
            metrics=[
                Metric(
                    key="five-hours",
                    name="5-hour window",
                    usage=Usage(percentage=42.0),
                    observed_at=now,
                )
            ],
        )
    # end def
# end class


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


@pytest.mark.asyncio
async def test_stale_result_is_not_treated_as_a_crawl_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AI_USAGE_CREDENTIAL_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    paths = temporary_paths(tmp_path)
    paths.ensure()
    database = Database(paths)
    await database.migrate()
    history = HistoryStore(paths, database)
    config = ConfigStore(paths)
    account = AccountConfig(
        id="stale-account",
        service="test-service",
        provider="stale",
        name="Stale account",
    )
    registry = ProviderRegistry()
    registry.register(StaleProvider())
    messages: list[str] = []
    collector = Collector(config, database, history, registry, reporter=messages.append)

    result = await collector.fetch_account(account, operation="crawling")
    assert result.status == FetchStatus.STALE
    assert any(
        "no new statusline data yet" in message and "reusing last known values" in message
        for message in messages
    )
    assert not any(message.startswith("Failed crawling") for message in messages)

    crawler = Crawler(collector, config, database, reporter=messages.append)
    await crawler.ensure_states([account])
    now = datetime.now(UTC)
    await crawler.update_state(account, result, now)

    assert not any("backing off crawl interval" in message for message in messages)

    async with database.sessions() as session:
        from ai_usage.orm import CrawlStateRecord

        state = await session.get(CrawlStateRecord, account.id)
        assert state is not None
        expected = now + timedelta(seconds=STALE_RECHECK_SECONDS)
        assert abs((state.next_run_at.replace(tzinfo=UTC) - expected).total_seconds()) < 1
        assert state.failure_count == 0
    # end with
    await database.close()
# end def


@pytest.mark.asyncio
async def test_tick_reports_account_and_git_backup_changes(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AI_USAGE_CREDENTIAL_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    paths = temporary_paths(tmp_path)
    paths.ensure()
    database = Database(paths)
    await database.migrate()
    history = HistoryStore(paths, database)
    config = ConfigStore(paths)
    registry = ProviderRegistry()
    registry.register(ChangingProvider())
    messages: list[str] = []
    collector = Collector(config, database, history, registry, reporter=messages.append)
    crawler = Crawler(collector, config, database, reporter=messages.append)

    await crawler.tick()
    assert not any("Config reload" in message for message in messages)

    account = AccountConfig(
        id="reload-account", service="test-service", provider="changing", name="Reload account"
    )
    config.save_account(account)
    await crawler.tick()
    assert any("account added" in message and "reload-account" in message for message in messages)

    messages.clear()
    disabled = account.model_copy(update={"enabled": False})
    config.save_account(disabled)
    await crawler.tick()
    assert any(
        "account removed or disabled" in message and "reload-account" in message
        for message in messages
    )

    messages.clear()
    config.save_global_config({"git": {"enabled": True}})
    await crawler.tick()
    assert any("git backup enabled" in message for message in messages)

    messages.clear()
    config.save_global_config({"git": {"enabled": False}})
    await crawler.tick()
    assert any("git backup disabled" in message for message in messages)

    await database.close()
# end def


def test_crawler_filters_accounts_restricted_to_other_hosts() -> None:
    unrestricted = AccountConfig(id="a", service="s", provider="p", name="Unrestricted")
    allowed = AccountConfig(
        id="b", service="s", provider="p", name="Allowed", hosts=[("laptop", "this-host")]
    )
    disallowed = AccountConfig(
        id="c", service="s", provider="p", name="Disallowed", hosts=[("desktop", "other-host")]
    )
    crawler = Crawler.__new__(Crawler)
    crawler.host_id = "this-host"

    filtered = crawler.accounts_for_this_host([unrestricted, allowed, disallowed])

    assert [account.id for account in filtered] == ["a", "b"]
# end def


def test_crawler_without_host_id_applies_no_filtering() -> None:
    restricted = AccountConfig(id="a", service="s", provider="p", name="Restricted", hosts=[("x", "y")])
    crawler = Crawler.__new__(Crawler)
    crawler.host_id = None

    assert crawler.accounts_for_this_host([restricted]) == [restricted]
# end def


class IdentityProvider(Provider):
    service = "test-service"
    key = "identity"
    display_name = "Identity test provider"

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
                    usage=Usage(percentage=1.0),
                    observed_at=now,
                )
            ],
            identity=AccountIdentity(name="AbelmannConsulting", email="user@example.com"),
            subscription=SubscriptionStatus(plan_type="stripe_subscription", status="active"),
            raw_payload={"secret": "do-not-leak-into-git"},
        )
    # end def
# end class


@pytest.mark.asyncio
async def test_fetch_persists_identity_subscription_and_raw_payload(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AI_USAGE_CREDENTIAL_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    paths = temporary_paths(tmp_path)
    paths.ensure()
    database = Database(paths)
    await database.migrate()
    history = HistoryStore(paths, database)
    config = ConfigStore(paths)
    account = AccountConfig(
        id="identity-account", service="test-service", provider="identity", name="Test"
    )
    config.save_account(account)
    registry = ProviderRegistry()
    registry.register(IdentityProvider())
    collector = Collector(config, database, history, registry)

    await collector.fetch_account(account)

    reloaded = config.get_account("identity-account")
    assert reloaded.identity is not None
    assert reloaded.identity.name == "AbelmannConsulting"
    assert reloaded.subscription is not None
    assert reloaded.subscription.plan_type == "stripe_subscription"

    raw_file = paths.local / "raw" / "test-service-identity-account.json"
    assert raw_file.exists()
    assert "do-not-leak-into-git" in raw_file.read_text(encoding="utf-8")
    await database.close()
# end def
