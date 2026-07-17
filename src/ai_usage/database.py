"""Async database lifecycle and encrypted credential repository."""

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from ai_usage.crypto import CredentialCipher, EncryptedValue
from ai_usage.orm import CredentialRecord, SourceRecord
from ai_usage.settings import Paths
from ai_usage.sqlite_compat import install_inline_sqlite_driver

install_inline_sqlite_driver()


def sqlite_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path}"
# end def


class Database:
    def __init__(self, paths: Paths):
        self.paths = paths
        self.engine: AsyncEngine = create_async_engine(sqlite_url(paths.database))
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.cipher = CredentialCipher.load(paths.credential_key)

        @event.listens_for(self.engine.sync_engine, "connect")
        def configure_sqlite(connection: Any, connection_record: Any) -> None:
            del connection_record
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()
        # end def
    # end def

    async def close(self) -> None:
        await self.engine.dispose()
    # end def

    async def migrate(self) -> None:
        self.paths.ensure()
        config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
        config.set_main_option("sqlalchemy.url", f"sqlite:///{self.paths.database}")
        command.upgrade(config, "head")
        os.chmod(self.paths.database, 0o600)
    # end def

    async def source_id(self) -> str:
        async with self.sessions() as session:
            result = await session.scalars(select(SourceRecord).limit(1))
            source = result.first()
            if source is None:
                source = SourceRecord(id=str(uuid.uuid4()), created_at=datetime.now(UTC))
                session.add(source)
                await session.commit()
            # end if
            return source.id
        # end with
    # end def

    async def put_credential(self, provider: str, name: str, value: dict[str, Any]) -> str:
        credential_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        encrypted = self.cipher.encrypt(
            json.dumps(value, separators=(",", ":"), sort_keys=True).encode(),
            credential_id.encode(),
        )
        async with self.sessions() as session:
            session.add(
                CredentialRecord(
                    id=credential_id,
                    provider=provider,
                    name=name,
                    ciphertext=encrypted.ciphertext,
                    nonce=encrypted.nonce,
                    encryption_version=encrypted.version,
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.commit()
        # end with
        return credential_id
    # end def

    async def get_credential(self, credential_id: str) -> dict[str, Any]:
        async with self.sessions() as session:
            record = await session.get(CredentialRecord, credential_id)
            if record is None:
                raise KeyError(f"credential {credential_id} is not available on this machine")
            # end if
            decrypted = self.cipher.decrypt(
                EncryptedValue(
                    ciphertext=record.ciphertext,
                    nonce=record.nonce,
                    version=record.encryption_version,
                ),
                credential_id.encode(),
            )
        # end with
        parsed: dict[str, Any] = json.loads(decrypted)
        return parsed
    # end def
# end class
