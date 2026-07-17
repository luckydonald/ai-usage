from datetime import UTC, datetime, timedelta

from ai_usage.graph import build_series
from ai_usage.orm import MetricSampleRecord


def sample(event_id: str, at: datetime, percentage: float, reset: datetime) -> MetricSampleRecord:
    return MetricSampleRecord(
        event_id=event_id,
        source_path="history.jsonl",
        source_id="source",
        service="codex",
        provider="app-server",
        account_id="account",
        metric_key="five-hours",
        metric_name="Five hours",
        observed_at=at,
        reset_at=reset,
        window_seconds=5 * 3600,
        usage_kind="percentage",
        percentage=percentage,
        metadata_json="{}",
    )
# end def


def test_graph_builds_step_points_window_and_projection() -> None:
    now = datetime(2026, 7, 17, 12, tzinfo=UTC)
    reset = now + timedelta(hours=2)
    records = [
        sample("one", now - timedelta(hours=2), 10, reset),
        sample("two", now - timedelta(hours=1), 30, reset),
    ]
    series = build_series(records, now=now)[0]
    assert [point.percentage for point in series.points] == [10, 30]
    assert series.windows[0].current is True
    assert series.windows[0].projected_end_percentage == 90
    assert series.windows[0].start == reset - timedelta(hours=5)
# end def


def test_graph_marks_exhausted_interval() -> None:
    now = datetime(2026, 7, 17, 12, tzinfo=UTC)
    reset = now + timedelta(hours=1)
    records = [sample("one", now - timedelta(minutes=10), 100, reset)]
    window = build_series(records, now=now)[0].windows[0]
    assert window.exhausted_from == now - timedelta(minutes=10)
    assert window.maximum_percentage == 100
# end def

