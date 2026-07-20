"""Typed SQLAlchemy persistence models."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass
# end class


class CredentialRecord(Base):
    __tablename__ = "credential"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(160))
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    nonce: Mapped[bytes] = mapped_column(LargeBinary)
    encryption_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
# end class


class SourceRecord(Base):
    __tablename__ = "source"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
# end class


class IndexedFileRecord(Base):
    __tablename__ = "indexed_file"

    path: Mapped[str] = mapped_column(Text, primary_key=True)
    size: Mapped[int] = mapped_column(Integer)
    modified_ns: Mapped[int] = mapped_column(Integer)
    byte_offset: Mapped[int] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
# end class


class MetricSampleRecord(Base):
    __tablename__ = "metric_sample"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_path: Mapped[str] = mapped_column(Text, index=True)
    source_id: Mapped[str] = mapped_column(String(36), index=True)
    service: Mapped[str] = mapped_column(String(80), index=True)
    provider: Mapped[str] = mapped_column(String(80), index=True)
    account_id: Mapped[str] = mapped_column(String(36), index=True)
    metric_key: Mapped[str] = mapped_column(String(120), index=True)
    metric_name: Mapped[str] = mapped_column(String(200))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    usage_kind: Mapped[str] = mapped_column(String(20))
    percentage: Mapped[float] = mapped_column(Float)
    current_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    maximum_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(80), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
# end class


class FetchRunRecord(Base):
    __tablename__ = "fetch_run"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(36), index=True)
    provider: Mapped[str] = mapped_column(String(80), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
# end class


class CrawlStateRecord(Base):
    __tablename__ = "crawl_state"

    account_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    active_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    last_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
# end class

