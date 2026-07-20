"""Public Pydantic contracts used by providers, storage, API, and UI."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, computed_field, field_validator


class FetchStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    ERROR = "error"
    STALE = "stale"
# end class


class Usage(BaseModel):
    kind: Literal["percentage"] = "percentage"
    percentage: float = Field(ge=0, le=100)
# end class


class MinMaxUsage(BaseModel):
    kind: Literal["min_max"] = "min_max"
    current: float = Field(ge=0)
    maximum: float = Field(gt=0)
    unit: str

    @computed_field
    @property
    def percentage(self) -> float:
        return min(100.0, max(0.0, self.current / self.maximum * 100.0))
    # end def
# end class


UsageValue = Annotated[Usage | MinMaxUsage, Field(discriminator="kind")]


class Metric(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str
    usage: UsageValue
    observed_at: datetime
    reset_at: datetime | None = None
    window_seconds: int | None = Field(default=None, gt=0)
    model: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("observed_at", "reset_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("timestamps must include a timezone")
        # end if
        return value.astimezone(UTC) if value is not None else None
    # end def
# end class


class AccountIdentity(BaseModel):
    """Common, provider-agnostic identity fields used to tell accounts apart."""

    name: str | None = None
    email: str | None = None
# end class


class SubscriptionStatus(BaseModel):
    """Common, provider-agnostic subscription/billing fields."""

    plan_type: str | None = None
    status: str | None = None
    renews_at: datetime | None = None
    cancel_at: datetime | None = None

    @field_validator("renews_at", "cancel_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("timestamps must include a timezone")
        # end if
        return value.astimezone(UTC) if value is not None else None
    # end def
# end class


class GitBackupConfig(BaseModel):
    """Shared setting controlling the debounced git commit/push of the data directory."""

    enabled: bool = False
# end class


class GlobalConfig(BaseModel):
    """Structured view of `config.yml`'s known sections; unknown keys are preserved via `extra`."""

    model_config = {"extra": "allow"}

    git: GitBackupConfig = Field(default_factory=GitBackupConfig)
# end class


class ProviderFetchResult(BaseModel):
    service: str
    provider: str
    account_id: str
    fetched_at: datetime
    status: FetchStatus = FetchStatus.SUCCESS
    metrics: list[Metric] = Field(default_factory=list)
    error: str | None = None
    identity: AccountIdentity | None = None
    subscription: SubscriptionStatus | None = None
    raw_payload: dict[str, Any] | None = None
# end class


class AccountConfig(BaseModel):
    id: str
    service: str
    provider: str
    name: str
    enabled: bool = True
    removed_at: datetime | None = None
    credential_id: str | None = None
    discovery_fingerprint: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    colors: dict[str, str] = Field(default_factory=dict)
    intervals: dict[str, int] = Field(default_factory=dict)
    hosts: list[tuple[str, str]] | None = None
    identity: AccountIdentity | None = None
    subscription: SubscriptionStatus | None = None
# end class


class HistoryEvent(BaseModel):
    schema_version: Literal[1] = 1
    event_id: str
    source_id: str
    service: str
    provider: str
    account_id: str
    metric: Metric
# end class


class GraphPoint(BaseModel):
    at: datetime
    percentage: float
    current: float | None = None
    maximum: float | None = None
# end class


class GraphWindow(BaseModel):
    start: datetime
    end: datetime
    maximum_percentage: float
    exhausted_from: datetime | None = None
    current: bool = False
    projected_end_percentage: float | None = None
# end class


class GraphSeries(BaseModel):
    service: str
    provider: str
    account_id: str
    metric_key: str
    metric_name: str
    color: str
    points: list[GraphPoint]
    windows: list[GraphWindow]
# end class
