"""Adaptive FastScheduler-backed crawling."""

import asyncio
import random
from datetime import UTC, datetime, timedelta

from fastscheduler import FastScheduler

from ai_usage.collector import Collector
from ai_usage.config import ConfigStore
from ai_usage.database import Database
from ai_usage.git_backup import maybe_run_git_backup
from ai_usage.host_identity import account_allows_host
from ai_usage.models import AccountConfig, FetchStatus, ProviderFetchResult
from ai_usage.orm import CrawlStateRecord
from ai_usage.progress import ProgressReporter, quiet_reporter

STALE_RECHECK_SECONDS = 10


def aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    # end if
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
# end def


class Crawler:
    def __init__(
        self,
        collector: Collector,
        config: ConfigStore,
        database: Database,
        reporter: ProgressReporter = quiet_reporter,
        host_id: str | None = None,
    ):
        self.collector = collector
        self.config = config
        self.database = database
        self.report = reporter
        self.host_id = host_id
        self.scheduler: FastScheduler | None = None
    # end def

    def accounts_for_this_host(self, accounts: list[AccountConfig]) -> list[AccountConfig]:
        if self.host_id is None:
            return accounts
        # end if
        return [account for account in accounts if account_allows_host(account, self.host_id)]
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
        accounts = self.accounts_for_this_host(self.config.list_accounts())
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
        results = await self.collector.fetch_all(due, operation="crawling")
        for account, result in zip(due, results, strict=True):
            await self.update_state(account, result, now)
        # end for
        await asyncio.to_thread(maybe_run_git_backup, self.database.paths, self.config, now)
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
                self.report(
                    f"{account.name}: backing off crawl interval to {backoff} seconds "
                    f"after failure {state.failure_count}."
                )
            elif result.status == FetchStatus.STALE:
                state.next_run_at = now + timedelta(seconds=STALE_RECHECK_SECONDS)
                state.failure_count = 0
                state.last_error = None
                self.report(
                    f"{account.name}: limits reported as stale, rechecking in "
                    f"{STALE_RECHECK_SECONDS} seconds."
                )
            else:
                previous_active_until = aware(state.active_until)
                was_active = previous_active_until is not None and previous_active_until > now
                percentage = max((metric.usage.percentage for metric in result.metrics), default=0.0)
                usage_increased = state.last_percentage is not None and percentage > state.last_percentage
                if usage_increased:
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
                if usage_increased and not was_active:
                    self.report(
                        f"{account.name}: decreasing crawl interval to "
                        f"{intervals['active_seconds']} seconds after usage increased."
                    )
                elif not usage_increased and not was_active and previous_active_until is not None:
                    self.report(
                        f"{account.name}: restoring crawl interval to "
                        f"{intervals['normal_seconds']} seconds."
                    )
                    state.active_until = None
                # end if
                self.report(f"{account.name}: next crawl in approximately {interval} seconds.")
            # end if
            await session.commit()
        # end with
    # end def

    async def run(self) -> None:
        accounts = self.accounts_for_this_host(self.config.list_accounts())
        if accounts:
            names = ", ".join(account.name for account in accounts)
            self.report(f"Crawler started for {len(accounts)} accounts: {names}.")
        else:
            self.report("Crawler started with no enabled accounts; waiting for configuration.")
        # end if
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
