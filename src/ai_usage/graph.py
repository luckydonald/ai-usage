"""Turn indexed samples into render-ready graph series."""

import colorsys
import hashlib
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from ai_usage.icons import IconRef
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

# One base brand color per service — every account/metric of that service is a deterministic
# lightness variant of this hue, so multiple accounts stay visually grouped by brand while still
# being distinguishable. Only a single shade per brand is used for now; the fuller brand palettes
# (e.g. codex's `#ee5091,#199fd7,#99bd3c,#fc7942,#8a50d8`) are reserved for later.
SERVICE_BASE_COLORS: dict[str, str] = {
    "codex": "#99bd3c",
    "claude": "#DE7356",
    "gemini": "#9177C7",
    "perplexity": "#21808D",
    "cursor": "#72716D",
}
LIGHTNESS_OFFSETS = (-0.18, -0.09, 0.0, 0.09, 0.18)

# Brand marks for the service filter chips. `copilot` has no Font Awesome Free icon of its own
# (checked: no `copilot`/`github-copilot`/`microsoft-copilot` constant exists in any version) —
# GitHub's mark is used as a stand-in.
SERVICE_ICONS: dict[str, IconRef] = {
    "claude": IconRef(set="brands", name="claude"),
    "codex": IconRef(set="brands", name="openai"),
    "copilot": IconRef(set="brands", name="github"),
}


def aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    # end if
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
# end def


def hex_to_rgb01(hex_color: str) -> tuple[float, float, float]:
    value = hex_color.lstrip("#")
    r, g, b = (int(value[index : index + 2], 16) / 255 for index in (0, 2, 4))
    return r, g, b
# end def


def rgb01_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(max(0.0, min(1.0, channel)) * 255):02x}" for channel in rgb)
# end def


def brand_color_variant(service: str, identity: str) -> str | None:
    base = SERVICE_BASE_COLORS.get(service)
    if base is None:
        return None
    # end if
    hue, lightness, saturation = colorsys.rgb_to_hls(*hex_to_rgb01(base))
    digest = hashlib.sha256(identity.encode()).digest()
    offset = LIGHTNESS_OFFSETS[digest[0] % len(LIGHTNESS_OFFSETS)]
    varied_lightness = min(0.92, max(0.08, lightness + offset))
    return rgb01_to_hex(colorsys.hls_to_rgb(hue, varied_lightness, saturation))
# end def


def generated_color(service: str, identity: str) -> str:
    variant = brand_color_variant(service, identity)
    if variant is not None:
        return variant
    # end if
    digest = hashlib.sha256(identity.encode()).digest()
    return PALETTE[int.from_bytes(digest[:2]) % len(PALETTE)]
# end def


def group_key(
    sample: MetricSampleRecord, account_groups: dict[str, str]
) -> tuple[str, str, str, str]:
    resolved_account_id = account_groups.get(sample.account_id, sample.account_id)
    provider = sample.provider if sample.account_id not in account_groups else "grouped"
    return sample.service, provider, resolved_account_id, sample.metric_key
# end def


def merge_duplicate_timestamps(points: list[GraphPoint]) -> list[GraphPoint]:
    """When grouped accounts both report a sample at the exact same timestamp, keep the higher
    percentage — the two sources are readings of the same underlying quota."""
    by_timestamp: dict[datetime, GraphPoint] = {}
    for point in points:
        existing = by_timestamp.get(point.at)
        if existing is None or point.percentage > existing.percentage:
            by_timestamp[point.at] = point
        # end if
    # end for
    return sorted(by_timestamp.values(), key=lambda point: point.at)
# end def


def build_series(
    samples: list[MetricSampleRecord],
    colors: dict[tuple[str, str], str] | None = None,
    now: datetime | None = None,
    account_groups: dict[str, str] | None = None,
) -> list[GraphSeries]:
    groups = account_groups or {}
    grouped: dict[tuple[str, str, str, str], list[MetricSampleRecord]] = defaultdict(list)
    for sample in samples:
        grouped[group_key(sample, groups)].append(sample)
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
        points = merge_duplicate_timestamps(points)
        windows = build_windows(metric_samples, current_time)
        points = with_window_reset_zeros(points, windows)
        color = configured_colors.get((account_id, metric_key)) or generated_color(
            service, "/".join(identity)
        )
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


def with_window_reset_zeros(
    points: list[GraphPoint], windows: list[GraphWindow]
) -> list[GraphPoint]:
    """Inject a synthetic 0% point at the end of every window that has already ended.

    Without this, the last real sample before a window's reset just sits at its last known
    percentage until the next window's first sample arrives, drawing a misleading gradual
    slope through the reset instead of the abrupt drop that actually happened.
    """
    existing_timestamps = {point.at for point in points}
    zero_points = [
        GraphPoint(at=window.end, percentage=0.0)
        for window in windows
        if not window.current and window.end not in existing_timestamps
    ]
    if not zero_points:
        return points
    # end if
    return sorted((*points, *zero_points), key=lambda point: point.at)
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

