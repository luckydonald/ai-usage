"""Adaptive FastScheduler-backed crawling."""

import asyncio
import random
from datetime import UTC, datetime, timedelta

from fastscheduler import FastScheduler

from ai_usage.collector import Collector
from ai_usage.config import ConfigStore
from ai_usage.database import Database
from ai_usage.git_backup import git_backup_enabled, maybe_run_git_backup
from ai_usage.host_identity import account_allows_host
from ai_usage.models import AccountConfig, FetchStatus, ProviderFetchResult
from ai_usage.notes import NotesStore
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
        self.known_account_ids: set[str] | None = None
        self.git_backup_was_enabled: bool | None = None
        self.notes_store = NotesStore(database.paths)
        self.known_active_notes: dict[str, set[str]] = {}
    # end def

    def report_account_changes(self, accounts: list[AccountConfig]) -> None:
        current_ids = {account.id for account in accounts}
        if self.known_account_ids is not None:
            by_id = {account.id: account for account in accounts}
            for added_id in current_ids - self.known_account_ids:
                account = by_id[added_id]
                label = f"{account.service}/{account.name} ({account.id})"
                self.report(f"Config reload: account added - {label}.")
            # end for
            for removed_id in self.known_account_ids - current_ids:
                self.report(f"Config reload: account removed or disabled - {removed_id}.")
            # end for
        # end if
        self.known_account_ids = current_ids
    # end def

    def report_git_backup_toggle(self) -> None:
        enabled = git_backup_enabled(self.config)
        if self.git_backup_was_enabled is not None and enabled != self.git_backup_was_enabled:
            self.report(f"Config reload: git backup {'enabled' if enabled else 'disabled'}.")
        # end if
        self.git_backup_was_enabled = enabled
    # end def

    def report_note_changes(
        self, account: AccountConfig, result: ProviderFetchResult, now: datetime
    ) -> None:
        known = self.known_active_notes.get(account.id)
        if known is None:
            known = self.notes_store.load_active_notes(account.service, account.id)
        # end if
        updated, transitions = self.notes_store.diff_and_record(
            account.service, account.id, result.notes, known, now
        )
        self.known_active_notes[account.id] = updated
        for transition in transitions:
            verb = "appeared" if transition.active else "disappeared"
            self.report(f"{account.name}: note {verb} - {transition.text}")
        # end for
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

    async def crawl(self, accounts: list[AccountConfig], reason: str) -> None:
        if not accounts:
            return
        # end if
        now = datetime.now(UTC)
        names = ", ".join(account.name for account in accounts)
        self.report(f"Crawling {len(accounts)} account(s) {reason}: {names}.")
        results = await self.collector.fetch_all(accounts, operation="crawling")
        for account, result in zip(accounts, results, strict=True):
            await self.update_state(account, result, now)
        # end for
        await asyncio.to_thread(maybe_run_git_backup, self.database.paths, self.config, now)
    # end def

    async def tick(self) -> None:
        accounts = self.accounts_for_this_host(self.config.list_accounts())
        self.report_account_changes(accounts)
        self.report_git_backup_toggle()
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
        await self.crawl(due, "due for a check")
    # end def

    async def update_state(
        self,
        account: AccountConfig,
        result: ProviderFetchResult,
        now: datetime,
    ) -> None:
        self.report_note_changes(account, result, now)
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
        await self.ensure_states(accounts)
        # Crawl right away instead of waiting for the first scheduled tick: a persisted
        # `next_run_at` from a previous run could be minutes/hours in the future (long-window
        # accounts back off their interval), which would otherwise leave a freshly (re)started
        # `up`/`crawl` showing stale numbers until that time arrives.
        await self.crawl(accounts, "immediately on startup")
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
