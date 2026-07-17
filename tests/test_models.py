from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ai_usage.models import Metric, MinMaxUsage, Usage


def test_min_max_percentage_is_normalized() -> None:
    usage = MinMaxUsage(current=75, maximum=50, unit="credits")
    assert usage.percentage == 100
# end def


def test_metric_requires_timezone() -> None:
    with pytest.raises(ValidationError):
        Metric(
            key="five-hours",
            name="Five hours",
            usage=Usage(percentage=20),
            observed_at=datetime(2026, 7, 17),
        )
    # end with


def test_metric_normalizes_timezone_to_utc() -> None:
    metric = Metric(
        key="five-hours",
        name="Five hours",
        usage=Usage(percentage=20),
        observed_at=datetime.now(UTC),
    )
    assert metric.observed_at.tzinfo == UTC
# end def

