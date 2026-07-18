"""Append-only Git-mergeable history and rebuildable SQLite indexing."""

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert

from ai_usage.database import Database
from ai_usage.models import HistoryEvent, Metric, MinMaxUsage, ProviderFetchResult
from ai_usage.orm import IndexedFileRecord, MetricSampleRecord
from ai_usage.settings import Paths


def metric_event_id(result: ProviderFetchResult, metric: Metric, source_id: str) -> str:
    identity = "\0".join(
        (
            result.service,
            result.provider,
            result.account_id,
            metric.key,
            metric.observed_at.isoformat(),
            metric.reset_at.isoformat() if metric.reset_at else "",
            source_id,
        )
    )
    return hashlib.sha256(identity.encode()).hexdigest()
# end def


class HistoryStore:
    def __init__(self, paths: Paths, database: Database):
        self.paths = paths
        self.database = database
    # end def

    def event_path(self, event: HistoryEvent) -> Path:
        observed = event.metric.observed_at.astimezone(UTC)
        return (
            self.paths.history
            / "v1"
            / event.service
            / event.account_id
            / event.metric.key
            / f"{observed:%Y}"
            / f"{observed:%m}"
            / f"{observed:%d}"
            / f"{event.source_id}.jsonl"
        )
    # end def

    async def append_result(self, result: ProviderFetchResult) -> list[HistoryEvent]:
        source_id = await self.database.source_id()
        events: list[HistoryEvent] = []
        for metric in result.metrics:
            event = HistoryEvent(
                event_id=metric_event_id(result, metric, source_id),
                source_id=source_id,
                service=result.service,
                provider=result.provider,
                account_id=result.account_id,
                metric=metric,
            )
            path = self.event_path(event)
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
                stream.write(event.model_dump_json() + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            # end with
            events.append(event)
            await self.index_file(path)
        # end for
        return events
    # end def

    async def latest_percentages(self, account_id: str) -> dict[str, float]:
        statement = (
            select(MetricSampleRecord)
            .where(MetricSampleRecord.account_id == account_id)
            .order_by(MetricSampleRecord.observed_at.desc())
        )
        async with self.database.sessions() as session:
            records = list(await session.scalars(statement))
        # end with
        latest: dict[str, float] = {}
        for record in records:
            latest.setdefault(record.metric_key, record.percentage)
        # end for
        return latest
    # end def

    async def index_all(self) -> int:
        count = 0
        for path in sorted(self.paths.history.glob("v1/**/*.jsonl")):
            count += await self.index_file(path)
        # end for
        return count
    # end def

    async def index_file(self, path: Path) -> int:
        relative = str(path.relative_to(self.paths.root))
        stat = path.stat()
        async with self.database.sessions() as session:
            indexed = await session.get(IndexedFileRecord, relative)
            offset = 0
            if indexed is not None and stat.st_size >= indexed.byte_offset:
                if stat.st_size == indexed.size and stat.st_mtime_ns == indexed.modified_ns:
                    return 0
                # end if
                offset = indexed.byte_offset
            elif indexed is not None:
                await session.execute(
                    delete(MetricSampleRecord).where(MetricSampleRecord.source_path == relative)
                )
            # end if

            added = 0
            error: str | None = None
            with path.open("rb") as stream:
                stream.seek(offset)
                while line := stream.readline():
                    try:
                        event = HistoryEvent.model_validate_json(line)
                        values = self.record_values(relative, event)
                        statement = insert(MetricSampleRecord).values(**values)
                        statement = statement.on_conflict_do_nothing(index_elements=["event_id"])
                        result = await session.execute(statement)
                        added += int(result.rowcount or 0)
                    except (ValueError, json.JSONDecodeError) as exception:
                        error = f"byte {stream.tell() - len(line)}: {exception}"
                    # end try
                # end while
                offset = stream.tell()
            # end with

            values = {
                "path": relative,
                "size": stat.st_size,
                "modified_ns": stat.st_mtime_ns,
                "byte_offset": offset,
                "error": error,
            }
            statement = insert(IndexedFileRecord).values(**values)
            statement = statement.on_conflict_do_update(index_elements=["path"], set_=values)
            await session.execute(statement)
            await session.commit()
            return added
        # end with
    # end def

    def record_values(self, relative: str, event: HistoryEvent) -> dict[str, object]:
        usage = event.metric.usage
        min_max = usage if isinstance(usage, MinMaxUsage) else None
        return {
            "event_id": event.event_id,
            "source_path": relative,
            "source_id": event.source_id,
            "service": event.service,
            "provider": event.provider,
            "account_id": event.account_id,
            "metric_key": event.metric.key,
            "metric_name": event.metric.name,
            "observed_at": event.metric.observed_at,
            "reset_at": event.metric.reset_at,
            "window_seconds": event.metric.window_seconds,
            "usage_kind": usage.kind,
            "percentage": usage.percentage,
            "current_value": min_max.current if min_max else None,
            "maximum_value": min_max.maximum if min_max else None,
            "unit": min_max.unit if min_max else None,
            "metadata_json": json.dumps(event.metric.metadata, separators=(",", ":"), sort_keys=True),
        }
    # end def

    async def samples(
        self,
        start: datetime,
        end: datetime,
        services: list[str] | None = None,
        providers: list[str] | None = None,
        accounts: list[str] | None = None,
        metrics: list[str] | None = None,
    ) -> list[MetricSampleRecord]:
        statement = (
            select(MetricSampleRecord)
            .where(MetricSampleRecord.observed_at >= start)
            .where(MetricSampleRecord.observed_at <= end)
            .order_by(MetricSampleRecord.observed_at)
        )
        for column, values in (
            (MetricSampleRecord.service, services),
            (MetricSampleRecord.provider, providers),
            (MetricSampleRecord.account_id, accounts),
            (MetricSampleRecord.metric_key, metrics),
        ):
            if values:
                statement = statement.where(column.in_(values))
            # end if
        # end for
        async with self.database.sessions() as session:
            result = await session.scalars(statement)
            return list(result)
        # end with
    # end def

    async def dedup(self, older_than_days: int = 7) -> dict[str, int]:
        """Drop consecutive same-value history lines older than `older_than_days`, keeping the first and last of each run."""
        root = self.paths.history / "v1"
        if not root.exists():
            return {"removed_lines": 0, "touched_files": 0}
        # end if
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
        removed_lines = 0
        touched_files = 0
        for metric_directory in sorted(path for path in root.glob("*/*/*") if path.is_dir()):
            files = sorted(metric_directory.glob("**/*.jsonl"))
            if not files:
                continue
            # end if
            removed, touched = await self._dedup_metric_stream(files, cutoff)
            removed_lines += removed
            touched_files += touched
        # end for
        return {"removed_lines": removed_lines, "touched_files": touched_files}
    # end def

    async def _dedup_metric_stream(self, files: list[Path], cutoff: datetime) -> tuple[int, int]:
        parsed: list[tuple[Path, str, tuple[float, float | None, float | None], datetime]] = []
        for file in files:
            for line in file.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                # end if
                event = HistoryEvent.model_validate_json(line)
                usage = event.metric.usage
                min_max = usage if isinstance(usage, MinMaxUsage) else None
                value_key = (usage.percentage, min_max.current if min_max else None, min_max.maximum if min_max else None)
                parsed.append((file, line, value_key, event.metric.observed_at.astimezone(UTC)))
            # end for
        # end for
        if len(parsed) < 3:
            return 0, 0
        # end if

        keep = [True] * len(parsed)
        index = 0
        while index < len(parsed):
            run_end = index
            while run_end + 1 < len(parsed) and parsed[run_end + 1][2] == parsed[index][2]:
                run_end += 1
            # end while
            for middle in range(index + 1, run_end):
                if parsed[middle][3] < cutoff:
                    keep[middle] = False
                # end if
            # end for
            index = run_end + 1
        # end while

        removed = keep.count(False)
        if removed == 0:
            return 0, 0
        # end if

        by_file: dict[Path, list[str | None]] = {}
        for (file, line, _value, _observed), kept in zip(parsed, keep, strict=True):
            by_file.setdefault(file, []).append(line if kept else None)
        # end for

        touched = 0
        for file, lines in by_file.items():
            surviving = [line for line in lines if line is not None]
            if len(surviving) == len(lines):
                continue
            # end if
            file.write_text("\n".join(surviving) + ("\n" if surviving else ""), encoding="utf-8")
            touched += 1
            relative = str(file.relative_to(self.paths.root))
            async with self.database.sessions() as session:
                await session.execute(
                    delete(MetricSampleRecord).where(MetricSampleRecord.source_path == relative)
                )
                await session.execute(delete(IndexedFileRecord).where(IndexedFileRecord.path == relative))
                await session.commit()
            # end with
            await self.index_file(file)
        # end for
        return removed, touched
    # end def
# end class
