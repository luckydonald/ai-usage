"""Python 3.14 compatibility adapter for SQLAlchemy's aiosqlite dialect.

The Fedora Python 3.14 sqlite module currently prevents an asyncio loop from
being woken after sqlite is opened in another thread.  aiosqlite therefore
never completes its connection future.  This adapter preserves SQLAlchemy's
async engine/session API while executing the small local SQLite operations on
the event-loop thread.  It can be disabled once the runtime issue is fixed.
"""

import asyncio
import os
import sqlite3
import sys
from collections.abc import Iterable
from types import SimpleNamespace
from typing import Any


class ImmediateQueue:
    def put_nowait(self, item: tuple[asyncio.Future[Any] | None, Any]) -> None:
        future, function = item
        try:
            result = function()
            if future is not None and not future.done():
                future.set_result(result)
            # end if
        except BaseException as exception:
            if future is not None and not future.done():
                future.set_exception(exception)
            # end if
        # end try
    # end def
# end class


class InlineCursor:
    def __init__(self, cursor: sqlite3.Cursor):
        self.cursor = cursor
    # end def

    @property
    def description(self) -> Any:
        return self.cursor.description
    # end def

    @property
    def lastrowid(self) -> int | None:
        return self.cursor.lastrowid
    # end def

    @property
    def rowcount(self) -> int:
        return self.cursor.rowcount
    # end def

    async def execute(self, operation: str, parameters: Any = ()) -> "InlineCursor":
        self.cursor.execute(operation, parameters)
        return self
    # end def

    async def executemany(self, operation: str, parameters: Iterable[Any]) -> "InlineCursor":
        self.cursor.executemany(operation, parameters)
        return self
    # end def

    async def fetchall(self) -> list[Any]:
        return self.cursor.fetchall()
    # end def

    async def fetchone(self) -> Any:
        return self.cursor.fetchone()
    # end def

    async def close(self) -> None:
        self.cursor.close()
    # end def
# end class


class InlineConnection:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        # SQLAlchemy's aiosqlite adapter intentionally uses these upstream
        # implementation attributes for isolation-level changes.
        self._conn = connection
        self._tx = ImmediateQueue()
    # end def

    @property
    def isolation_level(self) -> str | None:
        return self.connection.isolation_level
    # end def

    @isolation_level.setter
    def isolation_level(self, value: str | None) -> None:
        self.connection.isolation_level = value
    # end def

    async def cursor(self) -> InlineCursor:
        return InlineCursor(self.connection.cursor())
    # end def

    async def execute(self, operation: str, parameters: Any = ()) -> InlineCursor:
        cursor = InlineCursor(self.connection.cursor())
        return await cursor.execute(operation, parameters)
    # end def

    async def create_function(self, *args: Any, **kwargs: Any) -> None:
        self.connection.create_function(*args, **kwargs)
    # end def

    async def rollback(self) -> None:
        self.connection.rollback()
    # end def

    async def commit(self) -> None:
        self.connection.commit()
    # end def

    async def close(self) -> None:
        self.connection.close()
    # end def

    def stop(self) -> None:
        self.connection.close()
    # end def
# end class


class InlineConnect:
    def __init__(self, *args: Any, **kwargs: Any):
        self.args = args
        self.kwargs = kwargs
        # SQLAlchemy sets daemon on the contained thread in aiosqlite 0.22+.
        self._thread = SimpleNamespace(daemon=False)
    # end def

    async def connect(self) -> InlineConnection:
        return InlineConnection(sqlite3.connect(*self.args, **self.kwargs))
    # end def

    def __await__(self) -> Any:
        return self.connect().__await__()
    # end def
# end class


def install_inline_sqlite_driver() -> None:
    if sys.version_info < (3, 14):
        return
    # end if
    if os.environ.get("AI_USAGE_NATIVE_AIOSQLITE") == "1":
        return
    # end if
    import aiosqlite

    aiosqlite.connect = InlineConnect  # type: ignore[assignment]
# end def

