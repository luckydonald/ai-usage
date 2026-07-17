"""Turn indexed samples into render-ready graph series."""

import hashlib
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from ai_usage.models import GraphPoint, GraphSeries, GraphWindow
from ai_usage.orm import MetricSampleRecord

PALETTE = (
    "#f97316",
    "#8b5cf6",
    "#0ea5e9",
    "#10b981",
    "#e11d48",
    "#eab308",
    "#14b8a6",
    "#6366f1",
)


def aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    # end if
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
# end def


def generated_color(identity: str) -> str:
    digest = hashlib.sha256(identity.encode()).digest()
    return PALETTE[int.from_bytes(digest[:2]) % len(PALETTE)]
# end def


def group_key(sample: MetricSampleRecord) -> tuple[str, str, str, str]:
    return sample.service, sample.provider, sample.account_id, sample.metric_key
# end def


def build_series(
    samples: list[MetricSampleRecord],
    colors: dict[tuple[str, str], str] | None = None,
    now: datetime | None = None,
) -> list[GraphSeries]:
    grouped: dict[tuple[str, str, str, str], list[MetricSampleRecord]] = defaultdict(list)
    for sample in samples:
        grouped[group_key(sample)].append(sample)
    # end for
    current_time = now or datetime.now(UTC)
    configured_colors = colors or {}
    result: list[GraphSeries] = []
    for identity, metric_samples in sorted(grouped.items()):
        metric_samples.sort(key=lambda sample: aware(sample.observed_at) or current_time)
        service, provider, account_id, metric_key = identity
        points = [
            GraphPoint(
                at=aware(sample.observed_at) or current_time,
                percentage=sample.percentage,
                current=sample.current_value,
                maximum=sample.maximum_value,
            )
            for sample in metric_samples
        ]
        windows = build_windows(metric_samples, current_time)
        color = configured_colors.get((account_id, metric_key)) or generated_color("/".join(identity))
        result.append(
            GraphSeries(
                service=service,
                provider=provider,
                account_id=account_id,
                metric_key=metric_key,
                metric_name=metric_samples[0].metric_name,
                color=color,
                points=points,
                windows=windows,
            )
        )
    # end for
    return result
# end def


def build_windows(samples: list[MetricSampleRecord], now: datetime) -> list[GraphWindow]:
    grouped: dict[tuple[datetime | None, int | None], list[MetricSampleRecord]] = defaultdict(list)
    for sample in samples:
        grouped[(aware(sample.reset_at), sample.window_seconds)].append(sample)
    # end for
    windows: list[GraphWindow] = []
    for (reset_at, window_seconds), window_samples in sorted(
        grouped.items(), key=lambda item: item[0][0] or aware(item[1][0].observed_at) or now
    ):
        window_samples.sort(key=lambda sample: aware(sample.observed_at) or now)
        first_at = aware(window_samples[0].observed_at) or now
        last_at = aware(window_samples[-1].observed_at) or now
        start = (
            reset_at - timedelta(seconds=window_seconds)
            if reset_at is not None and window_seconds is not None
            else first_at
        )
        end = reset_at or last_at
        maximum = max(sample.percentage for sample in window_samples)
        exhausted = next(
            (aware(sample.observed_at) for sample in window_samples if sample.percentage >= 100),
            None,
        )
        current = end > now
        projection = projected_percentage(window_samples, end) if current else None
        windows.append(
            GraphWindow(
                start=start,
                end=end,
                maximum_percentage=maximum,
                exhausted_from=exhausted,
                current=current,
                projected_end_percentage=projection,
            )
        )
    # end for
    return windows
# end def


def projected_percentage(samples: list[MetricSampleRecord], end: datetime) -> float | None:
    if len(samples) < 2:
        return None
    # end if
    first = samples[0]
    last = samples[-1]
    first_at = aware(first.observed_at)
    last_at = aware(last.observed_at)
    if first_at is None or last_at is None:
        return None
    # end if
    elapsed = (last_at - first_at).total_seconds()
    delta = last.percentage - first.percentage
    if elapsed <= 0 or delta <= 0:
        return None
    # end if
    remaining = max(0.0, (end - last_at).total_seconds())
    return min(100.0, max(last.percentage, last.percentage + delta / elapsed * remaining))
# end def

