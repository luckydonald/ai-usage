"""Adaptive FastScheduler-backed crawling."""

import asyncio
import random
from datetime import UTC, datetime, timedelta

from fastscheduler import FastScheduler

from ai_usage.collector import Collector
from ai_usage.config import ConfigStore
from ai_usage.database import Database
from ai_usage.models import AccountConfig, FetchStatus, ProviderFetchResult
from ai_usage.orm import CrawlStateRecord


def aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    # end if
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
# end def


class Crawler:
    def __init__(self, collector: Collector, config: ConfigStore, database: Database):
        self.collector = collector
        self.config = config
        self.database = database
        self.scheduler: FastScheduler | None = None
    # end def

    async def ensure_states(self, accounts: list[AccountConfig]) -> None:
        now = datetime.now(UTC)
        async with self.database.sessions() as session:
            for account in accounts:
                state = await session.get(CrawlStateRecord, account.id)
                if state is None:
                    session.add(CrawlStateRecord(account_id=account.id, next_run_at=now))
                # end if
            # end for
            await session.commit()
        # end with
    # end def

    async def tick(self) -> None:
        accounts = self.config.list_accounts()
        await self.ensure_states(accounts)
        now = datetime.now(UTC)
        due: list[AccountConfig] = []
        async with self.database.sessions() as session:
            for account in accounts:
                state = await session.get(CrawlStateRecord, account.id)
                if state is not None and aware(state.next_run_at) <= now:
                    due.append(account)
                # end if
            # end for
        # end with
        if not due:
            return
        # end if
        results = await self.collector.fetch_all(due)
        for account, result in zip(due, results, strict=True):
            await self.update_state(account, result, now)
        # end for
    # end def

    async def update_state(
        self,
        account: AccountConfig,
        result: ProviderFetchResult,
        now: datetime,
    ) -> None:
        intervals = self.config.intervals_for(account)
        async with self.database.sessions() as session:
            state = await session.get(CrawlStateRecord, account.id)
            if state is None:
                state = CrawlStateRecord(account_id=account.id, next_run_at=now)
                session.add(state)
            # end if
            if result.status == FetchStatus.ERROR:
                state.failure_count += 1
                backoff = min(
                    intervals["maximum_backoff_seconds"],
                    intervals["active_seconds"] * (2 ** state.failure_count),
                )
                state.next_run_at = now + timedelta(seconds=backoff)
                state.last_error = result.error
            else:
                percentage = max((metric.usage.percentage for metric in result.metrics), default=0.0)
                if state.last_percentage is not None and percentage > state.last_percentage:
                    state.active_until = now + timedelta(seconds=intervals["active_for_seconds"])
                # end if
                active_until = aware(state.active_until)
                interval = (
                    intervals["active_seconds"]
                    if active_until is not None and active_until > now
                    else intervals["normal_seconds"]
                )
                jitter = random.uniform(0.95, 1.05)
                state.next_run_at = now + timedelta(seconds=interval * jitter)
                state.last_percentage = percentage
                state.failure_count = 0
                state.last_error = None
            # end if
            await session.commit()
        # end with
    # end def

    async def run(self) -> None:
        state_file = str(self.database.paths.local / "fastscheduler.json")
        self.scheduler = FastScheduler(state_file=state_file, quiet=True)
        self.scheduler.every(1).seconds.no_catch_up().do(self.tick)
        self.scheduler.start()
        try:
            while True:
                await asyncio.sleep(1)
            # end while
        finally:
            await asyncio.to_thread(self.scheduler.stop)
        # end try
    # end def
# end class

