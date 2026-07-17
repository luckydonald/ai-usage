"""FastAPI application, query API, static dashboard, and combined runtime."""

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Any

import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from ai_usage.collector import Collector
from ai_usage.config import ConfigStore
from ai_usage.crawler import Crawler
from ai_usage.database import Database
from ai_usage.graph import build_series
from ai_usage.history import HistoryStore
from ai_usage.orm import MetricSampleRecord
from ai_usage.providers import built_in_registry
from ai_usage.sentry import capture_exception, init_sentry
from ai_usage.settings import Paths

init_sentry()
LOGGER = logging.getLogger("ai_usage.api")


class ApplicationState:
    def __init__(self, paths: Paths):
        self.paths = paths
        self.database = Database(paths)
        self.config = ConfigStore(paths)
        self.history = HistoryStore(paths, self.database)
        self.providers = built_in_registry()
        self.collector = Collector(self.config, self.database, self.history, self.providers)
        self.crawler = Crawler(self.collector, self.config, self.database)
    # end def

    async def initialize(self) -> None:
        self.paths.ensure()
        await self.database.migrate()
        await self.history.index_all()
    # end def

    async def close(self) -> None:
        await self.database.close()
    # end def
# end class


def create_app(paths: Paths) -> FastAPI:
    state = ApplicationState(paths)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        del application
        try:
            await state.initialize()
        except Exception as exception:
            capture_exception(exception)
            raise
        # end try
        try:
            yield
        finally:
            await state.close()
        # end try
    # end def

    app = FastAPI(title="AI Usage", version="0.1.0", lifespan=lifespan)
    app.state.runtime = state

    @app.get("/api/v1/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}
    # end def

    @app.get("/api/v1/catalog")
    async def catalog() -> dict[str, Any]:
        accounts = state.config.list_accounts(False)
        async with state.database.sessions() as session:
            rows = await session.execute(
                select(
                    MetricSampleRecord.service,
                    MetricSampleRecord.provider,
                    MetricSampleRecord.account_id,
                    MetricSampleRecord.metric_key,
                    MetricSampleRecord.metric_name,
                ).distinct()
            )
            metrics = [dict(row._mapping) for row in rows]
        # end with
        return {
            "accounts": [account.model_dump(mode="json") for account in accounts],
            "metrics": metrics,
            "exhausted_color": "#6b7280",
        }
    # end def

    @app.get("/api/v1/latest")
    async def latest() -> list[dict[str, Any]]:
        async with state.database.sessions() as session:
            result = await session.scalars(
                select(MetricSampleRecord).order_by(MetricSampleRecord.observed_at.desc())
            )
            records = list(result)
        # end with
        seen: set[tuple[str, str]] = set()
        latest_rows: list[dict[str, Any]] = []
        for record in records:
            identity = record.account_id, record.metric_key
            if identity in seen:
                continue
            # end if
            seen.add(identity)
            latest_rows.append(record_payload(record))
        # end for
        return latest_rows
    # end def

    @app.get("/api/v1/series")
    async def series(
        start: datetime,
        end: datetime,
        service: Annotated[list[str] | None, Query()] = None,
        provider: Annotated[list[str] | None, Query()] = None,
        account: Annotated[list[str] | None, Query()] = None,
        metric: Annotated[list[str] | None, Query()] = None,
    ) -> list[dict[str, Any]]:
        samples = await state.history.samples(start, end, service, provider, account, metric)
        colors: dict[tuple[str, str], str] = {}
        for configured in state.config.list_accounts(False):
            for metric_key, color in configured.colors.items():
                colors[(configured.id, metric_key)] = color
            # end for
        # end for
        return [item.model_dump(mode="json") for item in build_series(samples, colors)]
    # end def

    @app.get("/api/v1/events")
    async def events() -> StreamingResponse:
        async def stream() -> AsyncIterator[str]:
            last_event = ""
            while True:
                async with state.database.sessions() as session:
                    record = await session.scalar(
                        select(MetricSampleRecord).order_by(MetricSampleRecord.observed_at.desc()).limit(1)
                    )
                # end with
                if record is not None and record.event_id != last_event:
                    last_event = record.event_id
                    yield f"id: {record.event_id}\nevent: sample\ndata: {json.dumps(record_payload(record))}\n\n"
                else:
                    yield ": keepalive\n\n"
                # end if
                await asyncio.sleep(2)
            # end while
        # end def

        return StreamingResponse(stream(), media_type="text/event-stream")
    # end def

    if os.environ.get("SENTRY_ENABLE_SAMPLE_ROUTES") == "1":
        @app.get("/api/v1/sentry/sample-error")
        async def sentry_sample_error() -> None:
            raise RuntimeError("backend sample error for Sentry/Bugsink verification")
        # end def
    # end if

    if paths.frontend.exists():
        assets = paths.frontend / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")
        # end if

        @app.get("/{path:path}", include_in_schema=False)
        async def frontend(path: str) -> FileResponse:
            candidate = paths.frontend / path
            if path and candidate.is_file() and paths.frontend in candidate.resolve().parents:
                return FileResponse(candidate)
            # end if
            return FileResponse(paths.frontend / "index.html")
        # end def
    else:
        @app.get("/", include_in_schema=False)
        async def placeholder() -> JSONResponse:
            return JSONResponse({"name": "AI Usage", "dashboard": "not built"})
        # end def
    # end if
    return app
# end def


def record_payload(record: MetricSampleRecord) -> dict[str, Any]:
    return {
        "event_id": record.event_id,
        "service": record.service,
        "provider": record.provider,
        "account_id": record.account_id,
        "metric_key": record.metric_key,
        "metric_name": record.metric_name,
        "observed_at": record.observed_at.isoformat(),
        "reset_at": record.reset_at.isoformat() if record.reset_at else None,
        "percentage": record.percentage,
        "current": record.current_value,
        "maximum": record.maximum_value,
        "unit": record.unit,
    }
# end def


def exposed_host(host: str) -> bool:
    return host not in {"localhost", "127.0.0.1", "::1"}
# end def


async def run_server_and_crawler(paths: Paths, host: str, port: int) -> None:
    if exposed_host(host):
        LOGGER.warning(
            "AI Usage is binding to %s without authentication; anyone who can reach the port can read usage data",
            host,
        )
    # end if
    app = create_app(paths)
    runtime: ApplicationState = app.state.runtime
    await runtime.initialize()
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, lifespan="off"))
    try:
        async with asyncio.TaskGroup() as group:
            group.create_task(runtime.crawler.run())
            group.create_task(server.serve())
        # end with
    finally:
        await runtime.close()
    # end try
# end def
