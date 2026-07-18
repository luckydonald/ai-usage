"""Configured provider-account status and removal operations."""

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete, select, update

from ai_usage.config import ConfigStore
from ai_usage.database import Database
from ai_usage.models import AccountConfig
from ai_usage.orm import (
    CrawlStateRecord,
    CredentialRecord,
    FetchRunRecord,
    IndexedFileRecord,
    MetricSampleRecord,
)
from ai_usage.settings import Paths


@dataclass(frozen=True, slots=True)
class LatestMetricStatus:
    key: str
    name: str
    percentage: float
    observed_at: datetime
    reset_at: datetime | None
# end class


@dataclass(frozen=True, slots=True)
class AccountStatus:
    account: AccountConfig
    credential_available: bool
    latest_metrics: list[LatestMetricStatus]
    last_fetch: FetchRunRecord | None
    crawl_state: CrawlStateRecord | None
# end class


def matching_accounts(
    config: ConfigStore,
    service: str | None = None,
    provider: str | None = None,
) -> list[AccountConfig]:
    return [
        account
        for account in config.list_accounts(False)
        if (service is None or account.service == service)
        and (provider is None or account.provider == provider)
    ]
# end def


async def account_status(database: Database, account: AccountConfig) -> AccountStatus:
    async with database.sessions() as session:
        credential_available = False
        if account.credential_id:
            credential_available = await session.get(CredentialRecord, account.credential_id) is not None
        # end if
        metric_records = list(
            await session.scalars(
                select(MetricSampleRecord)
                .where(MetricSampleRecord.account_id == account.id)
                .order_by(MetricSampleRecord.observed_at.desc())
            )
        )
        last_fetch = await session.scalar(
            select(FetchRunRecord)
            .where(FetchRunRecord.account_id == account.id)
            .order_by(FetchRunRecord.started_at.desc())
            .limit(1)
        )
        crawl_state = await session.get(CrawlStateRecord, account.id)
    # end with
    latest: dict[str, LatestMetricStatus] = {}
    for record in metric_records:
        latest.setdefault(
            record.metric_key,
            LatestMetricStatus(
                key=record.metric_key,
                name=record.metric_name,
                percentage=record.percentage,
                observed_at=record.observed_at,
                reset_at=record.reset_at,
            ),
        )
    # end for
    return AccountStatus(
        account=account,
        credential_available=credential_available,
        latest_metrics=list(latest.values()),
        last_fetch=last_fetch,
        crawl_state=crawl_state,
    )
# end def


async def remove_local_state(database: Database, account: AccountConfig) -> None:
    async with database.sessions() as session:
        await session.execute(delete(CrawlStateRecord).where(CrawlStateRecord.account_id == account.id))
        await session.execute(delete(FetchRunRecord).where(FetchRunRecord.account_id == account.id))
        if account.credential_id:
            await session.execute(
                delete(CredentialRecord).where(CredentialRecord.id == account.credential_id)
            )
        # end if
        await session.commit()
    # end with
# end def


def account_history_root(paths: Paths, account: AccountConfig) -> Path:
    return paths.history / "v1" / account.service / account.id
# end def


async def merge_account_history(
    paths: Paths,
    database: Database,
    source: AccountConfig,
    target: AccountConfig,
) -> None:
    """Move `source`'s samples/history/credential ownership into `target`, then drop `source`'s runtime state."""
    source_root = account_history_root(paths, source)
    target_root = account_history_root(paths, target)
    async with database.sessions() as session:
        await session.execute(
            update(MetricSampleRecord)
            .where(MetricSampleRecord.account_id == source.id)
            .values(account_id=target.id)
        )
        await session.execute(
            update(FetchRunRecord).where(FetchRunRecord.account_id == source.id).values(account_id=target.id)
        )
        await session.execute(delete(CrawlStateRecord).where(CrawlStateRecord.account_id == source.id))

        if source_root.exists():
            if target_root.exists():
                for child in source_root.rglob("*"):
                    if not child.is_file():
                        continue
                    # end if
                    destination = target_root / child.relative_to(source_root)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    child.replace(destination)
                # end for
                shutil.rmtree(source_root, ignore_errors=True)
            else:
                target_root.parent.mkdir(parents=True, exist_ok=True)
                source_root.replace(target_root)
            # end if
        # end if

        source_prefix = str(source_root.relative_to(paths.root))
        target_prefix = str(target_root.relative_to(paths.root))
        indexed_rows = list(
            await session.scalars(
                select(IndexedFileRecord).where(IndexedFileRecord.path.like(f"{source_prefix}/%"))
            )
        )
        for row in indexed_rows:
            new_path = target_prefix + row.path[len(source_prefix):]
            if await session.get(IndexedFileRecord, new_path) is not None:
                await session.delete(row)
            else:
                row.path = new_path
            # end if
        # end for

        if source.credential_id:
            await session.execute(delete(CredentialRecord).where(CredentialRecord.id == source.credential_id))
        # end if
        await session.commit()
    # end with
# end def


async def purge_history(paths: Paths, database: Database, account: AccountConfig) -> None:
    history_root = account_history_root(paths, account)
    expected_parent = paths.history / "v1" / account.service
    if history_root.parent != expected_parent or history_root.name != account.id:
        raise ValueError("refusing to purge an unresolved account history path")
    # end if
    if history_root.exists():
        shutil.rmtree(history_root)
    # end if
    relative_prefix = str(history_root.relative_to(paths.root)) + "/%"
    async with database.sessions() as session:
        await session.execute(
            delete(MetricSampleRecord).where(MetricSampleRecord.account_id == account.id)
        )
        await session.execute(
            delete(IndexedFileRecord).where(IndexedFileRecord.path.like(relative_prefix))
        )
        await session.commit()
    # end with
# end def
