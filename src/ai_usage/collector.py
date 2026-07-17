"""Provider orchestration and durable fetch-run recording."""

import asyncio
import uuid
from datetime import UTC, datetime

from ai_usage.config import ConfigStore
from ai_usage.database import Database
from ai_usage.history import HistoryStore
from ai_usage.models import AccountConfig, FetchStatus, ProviderFetchResult
from ai_usage.orm import FetchRunRecord
from ai_usage.providers import ProviderRegistry


class Collector:
    def __init__(
        self,
        config: ConfigStore,
        database: Database,
        history: HistoryStore,
        providers: ProviderRegistry,
    ) -> None:
        self.config = config
        self.database = database
        self.history = history
        self.providers = providers
        self.account_locks: dict[str, asyncio.Lock] = {}
    # end def

    async def fetch_account(self, account: AccountConfig) -> ProviderFetchResult:
        lock = self.account_locks.setdefault(account.id, asyncio.Lock())
        async with lock:
            started = datetime.now(UTC)
            run_id = str(uuid.uuid4())
            async with self.database.sessions() as session:
                session.add(
                    FetchRunRecord(
                        id=run_id,
                        account_id=account.id,
                        provider=account.provider,
                        started_at=started,
                        success=False,
                    )
                )
                await session.commit()
            # end with
            try:
                credential = None
                if account.credential_id:
                    credential = await self.database.get_credential(account.credential_id)
                # end if
                provider = self.providers.get(account.service, account.provider)
                result = await provider.fetch(account, credential)
                await self.history.append_result(result)
                success = True
                error = None
            except Exception as exception:
                success = False
                error = str(exception)
                result = ProviderFetchResult(
                    service=account.service,
                    provider=account.provider,
                    account_id=account.id,
                    fetched_at=datetime.now(UTC),
                    status=FetchStatus.ERROR,
                    error=error,
                )
            # end try
            async with self.database.sessions() as session:
                record = await session.get(FetchRunRecord, run_id)
                if record is not None:
                    record.finished_at = datetime.now(UTC)
                    record.success = success
                    record.error = error
                    await session.commit()
                # end if
            # end with
            return result
        # end with
    # end def

    async def fetch_all(self, accounts: list[AccountConfig] | None = None) -> list[ProviderFetchResult]:
        selected = accounts if accounts is not None else self.config.list_accounts()
        return list(await asyncio.gather(*(self.fetch_account(account) for account in selected)))
    # end def
# end class

