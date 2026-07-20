from datetime import UTC, datetime, timedelta

from ai_usage.graph import PALETTE, build_series, generated_color
from ai_usage.orm import MetricSampleRecord


def sample(
    event_id: str,
    at: datetime,
    percentage: float,
    reset: datetime,
    account_id: str = "account",
    provider: str = "app-server",
    service: str = "codex",
) -> MetricSampleRecord:
    return MetricSampleRecord(
        event_id=event_id,
        source_path="history.jsonl",
        source_id="source",
        service=service,
        provider=provider,
        account_id=account_id,
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


def test_graph_injects_zero_point_after_an_ended_window() -> None:
    now = datetime(2026, 7, 17, 12, tzinfo=UTC)
    reset = now - timedelta(hours=1)
    records = [
        sample("one", now - timedelta(hours=3), 10, reset),
        sample("two", now - timedelta(hours=2), 80, reset),
    ]
    series = build_series(records, now=now)[0]
    assert series.windows[0].current is False
    assert [(point.at, point.percentage) for point in series.points] == [
        (now - timedelta(hours=3), 10),
        (now - timedelta(hours=2), 80),
        (reset, 0),
    ]
# end def


def test_graph_does_not_duplicate_zero_point_when_a_real_sample_already_sits_at_reset() -> None:
    now = datetime(2026, 7, 17, 12, tzinfo=UTC)
    reset = now - timedelta(hours=1)
    records = [
        sample("one", now - timedelta(hours=2), 50, reset),
        sample("two", reset, 0, reset),
    ]
    series = build_series(records, now=now)[0]
    assert [point.at for point in series.points] == [now - timedelta(hours=2), reset]
# end def


def test_generated_color_stays_within_a_services_brand_hue() -> None:
    first = generated_color("codex", "codex/app-server/account-1/five-hours")
    second = generated_color("codex", "codex/app-server/account-2/five-hours")
    assert first != second
    assert first != "#99bd3c"

    import colorsys

    from ai_usage.graph import hex_to_rgb01

    base_hue = colorsys.rgb_to_hls(*hex_to_rgb01("#99bd3c"))[0]
    for color in (first, second):
        hue = colorsys.rgb_to_hls(*hex_to_rgb01(color))[0]
        assert abs(hue - base_hue) < 0.01
    # end for
# end def


def test_generated_color_falls_back_to_the_shared_palette_for_unbranded_services() -> None:
    color = generated_color("some-future-service", "some-future-service/x/account/metric")
    assert color in PALETTE
# end def


def test_build_series_uses_brand_color_for_known_services() -> None:
    now = datetime(2026, 7, 17, 12, tzinfo=UTC)
    reset = now + timedelta(hours=1)
    records = [sample("one", now, 10, reset)]
    series = build_series(records, now=now)[0]
    assert series.color == generated_color("codex", "codex/app-server/account/five-hours")
# end def


def test_graph_marks_exhausted_interval() -> None:
    now = datetime(2026, 7, 17, 12, tzinfo=UTC)
    reset = now + timedelta(hours=1)
    records = [sample("one", now - timedelta(minutes=10), 100, reset)]
    window = build_series(records, now=now)[0].windows[0]
    assert window.exhausted_from == now - timedelta(minutes=10)
    assert window.maximum_percentage == 100
# end def


def test_grouped_accounts_merge_into_a_single_series_under_the_group_id() -> None:
    now = datetime(2026, 7, 17, 12, tzinfo=UTC)
    reset = now + timedelta(hours=2)
    records = [
        sample(
            "one", now - timedelta(hours=2), 10, reset, account_id="laptop", provider="cli-usage"
        ),
        sample("two", now - timedelta(hours=1), 30, reset, account_id="web", provider="web"),
    ]
    series = build_series(records, now=now, account_groups={"laptop": "group-1", "web": "group-1"})
    assert len(series) == 1
    merged = series[0]
    assert merged.account_id == "group-1"
    assert merged.provider == "grouped"
    assert [point.percentage for point in merged.points] == [10, 30]
# end def


def test_grouped_accounts_keep_the_higher_percentage_for_overlapping_windows() -> None:
    now = datetime(2026, 7, 17, 12, tzinfo=UTC)
    reset = now + timedelta(hours=2)
    same_moment = now - timedelta(hours=1)
    records = [
        sample("one", same_moment, 40, reset, account_id="laptop", provider="cli-usage"),
        sample("two", same_moment, 65, reset, account_id="web", provider="web"),
    ]
    series = build_series(records, now=now, account_groups={"laptop": "group-1", "web": "group-1"})
    merged = series[0]
    assert [point.percentage for point in merged.points] == [65]
    assert merged.windows[0].maximum_percentage == 65
# end def


def test_ungrouped_accounts_remain_separate_series() -> None:
    now = datetime(2026, 7, 17, 12, tzinfo=UTC)
    reset = now + timedelta(hours=2)
    records = [
        sample("one", now - timedelta(hours=2), 10, reset, account_id="laptop"),
        sample("two", now - timedelta(hours=1), 30, reset, account_id="web"),
    ]
    series = build_series(records, now=now)
    assert {item.account_id for item in series} == {"laptop", "web"}
# end def

