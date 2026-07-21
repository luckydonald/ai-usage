import type { EChartsOption, SeriesOption } from "echarts";

import { renderNoteMarkdown } from "./markdown";
import { formatDuration, formatRelative } from "./time";
import type { GraphPoint, GraphSeries, GraphWindow, NoteRange } from "./types";

export function seriesDisplayName(item: GraphSeries, accountLabels: Record<string, string> = {}): string {
  const account = accountLabels[item.account_id] ?? item.account_id.slice(0, 8);
  return `${item.metric_name} · ${item.provider} · ${account}`;
}

export function seriesKey(item: GraphSeries): string {
  return `${item.account_id}::${item.metric_key}`;
}

const PERFECT_LANDING_TOLERANCE_PERCENT = 1;
const PERFECT_LANDING_MAX_GAP_MS = 15 * 60 * 1000;

export function windowByPoint(windows: GraphWindow[], at: string): GraphWindow | undefined {
  const time = new Date(at).getTime();
  return windows.find((window) => time >= new Date(window.start).getTime() && time <= new Date(window.end).getTime());
}

export function percentThroughWindow(pointAt: string, window: GraphWindow): number {
  const start = new Date(window.start).getTime();
  const end = new Date(window.end).getTime();
  const at = new Date(pointAt).getTime();
  if (end <= start) return 0;
  return Math.min(100, Math.max(0, ((at - start) / (end - start)) * 100));
}

export interface WindowStats {
  maximumPercentage: number;
  burnRatePerHour: number | null;
  exhaustedAfterMs: number | null;
  blockedForMs: number | null;
  remainingPercentageAtEnd: number | null;
  perfectLanding: boolean;
  projectedRemainingPercentageAtEnd: number | null;
  projectedExhaustedAt: string | null;
}

export function computeWindowStats(points: GraphPoint[], window: GraphWindow, now: Date): WindowStats {
  const start = new Date(window.start).getTime();
  const end = new Date(window.end).getTime();
  const inWindow = points
    .filter((point) => {
      const at = new Date(point.at).getTime();
      return at >= start && at <= end;
    })
    .sort((a, b) => new Date(a.at).getTime() - new Date(b.at).getTime());

  const exhaustedAfterMs = window.exhausted_from ? new Date(window.exhausted_from).getTime() - start : null;
  const blockedForMs = window.exhausted_from ? end - new Date(window.exhausted_from).getTime() : null;
  const remainingPercentageAtEnd =
    !window.current && !window.exhausted_from ? Math.max(0, 100 - window.maximum_percentage) : null;

  let burnRatePerHour: number | null = null;
  const last = inWindow.at(-1);
  if (last) {
    const relevantEndMs = window.exhausted_from ? new Date(window.exhausted_from).getTime() : new Date(last.at).getTime();
    const elapsedMs = relevantEndMs - start;
    if (elapsedMs > 0) {
      const value = window.exhausted_from ? 100 : window.maximum_percentage;
      burnRatePerHour = (value / elapsedMs) * (60 * 60 * 1000);
    }
  }

  let perfectLanding = false;
  if (inWindow.length >= 2 && Math.abs(last!.percentage - 100) <= PERFECT_LANDING_TOLERANCE_PERCENT) {
    const previous = inWindow.at(-2)!;
    const gapToPrevious = new Date(last!.at).getTime() - new Date(previous.at).getTime();
    const gapToWindowEnd = end - new Date(last!.at).getTime();
    perfectLanding = gapToPrevious <= PERFECT_LANDING_MAX_GAP_MS && gapToWindowEnd <= PERFECT_LANDING_MAX_GAP_MS;
  }

  let projectedRemainingPercentageAtEnd: number | null = null;
  let projectedExhaustedAt: string | null = null;
  if (window.current && !window.exhausted_from && window.projected_end_percentage !== null) {
    const projected = window.projected_end_percentage;
    if (projected < 100 - PERFECT_LANDING_TOLERANCE_PERCENT) {
      projectedRemainingPercentageAtEnd = 100 - projected;
    } else if (projected > 100 + PERFECT_LANDING_TOLERANCE_PERCENT && last && burnRatePerHour) {
      const hoursToExhaustion = (100 - last.percentage) / burnRatePerHour;
      projectedExhaustedAt = new Date(new Date(last.at).getTime() + hoursToExhaustion * 60 * 60 * 1000).toISOString();
    }
  }

  return {
    maximumPercentage: window.maximum_percentage,
    burnRatePerHour,
    exhaustedAfterMs,
    blockedForMs,
    remainingPercentageAtEnd,
    perfectLanding,
    projectedRemainingPercentageAtEnd,
    projectedExhaustedAt,
  };
}

function accountLabelFor(item: GraphSeries, accountLabels: Record<string, string>): string {
  return accountLabels[item.account_id] ?? item.account_id.slice(0, 8);
}

export function pointTooltipHtml(
  item: GraphSeries,
  point: GraphPoint,
  window: GraphWindow | undefined,
  accountLabels: Record<string, string>,
): string {
  const lines = [
    `<strong>${new Date(point.at).toLocaleString()}</strong>`,
    `Service: ${item.service}`,
    `Provider: ${item.provider}`,
    `Account: ${accountLabelFor(item, accountLabels)}`,
    `Usage: ${point.percentage.toFixed(1)}%`,
  ];
  if (window) {
    const remainingMs = new Date(window.end).getTime() - new Date(point.at).getTime();
    lines.push(
      `Window end: ${new Date(window.end).toLocaleString()} (${formatDuration(remainingMs)} away)`,
      `${percentThroughWindow(point.at, window).toFixed(0)}% through window`,
    );
  }
  return lines.join("<br/>");
}

// Relative time with the absolute timestamp as a native title tooltip — used only here, not in
// the hover tooltip's own separate `compactWindowDetail`, which already shows its own countdown.
function relativeTimeSpan(at: Date, now: Date): string {
  const absolute = at.toLocaleString();
  return `<span title="${absolute}">${formatRelative(at, now)}</span>`;
}

function windowDetailLines(item: GraphSeries, window: GraphWindow, now: Date): string[] {
  const stats = computeWindowStats(item.points, window, now);
  const lines = [
    `${relativeTimeSpan(new Date(window.start), now)} → ${relativeTimeSpan(new Date(window.end), now)}`,
    `Peak usage: ${stats.maximumPercentage.toFixed(1)}%`,
  ];
  if (stats.burnRatePerHour !== null) {
    lines.push(`Burn rate: ${stats.burnRatePerHour.toFixed(1)}%/h`);
  }
  if (stats.perfectLanding) {
    lines.push("Right on spot!");
  } else if (window.exhausted_from && stats.exhaustedAfterMs !== null && stats.blockedForMs !== null) {
    lines.push(`Hit 100% after ${formatDuration(stats.exhaustedAfterMs)}`, `Blocked for ${formatDuration(stats.blockedForMs)}`);
  } else if (stats.remainingPercentageAtEnd !== null) {
    lines.push(`${stats.remainingPercentageAtEnd.toFixed(1)}% remaining at window end`);
  } else if (stats.projectedRemainingPercentageAtEnd !== null) {
    lines.push(`Projected to land at ${(100 - stats.projectedRemainingPercentageAtEnd).toFixed(1)}%`, `${stats.projectedRemainingPercentageAtEnd.toFixed(1)}% of your limit would be left to use`);
  } else if (stats.projectedExhaustedAt !== null) {
    const exhaustedAt = new Date(stats.projectedExhaustedAt);
    lines.push(`At this rate, you'll hit 100% around ${relativeTimeSpan(exhaustedAt, now)}`);
  }
  return lines;
}

export function windowTooltipHtml(
  item: GraphSeries,
  window: GraphWindow,
  now: Date,
  accountLabels: Record<string, string>,
  includeHeader = true,
): string {
  const lines = includeHeader
    ? [`<strong>${accountLabelFor(item, accountLabels)} · ${item.provider} · ${item.metric_name}</strong>`]
    : [];
  lines.push(...windowDetailLines(item, window, now));
  return lines.join("<br/>");
}

export function noteTooltipHtml(note: NoteRange): string {
  const start = new Date(note.start).toLocaleDateString();
  const range = note.end ? `${start} → ${new Date(note.end).toLocaleDateString()}` : `${start} → now`;
  return [renderNoteMarkdown(note.text), range].join("<br/>");
}

// The step-line chart holds each series flat at its last recorded value until the next
// sample — so the value "at" any hovered timestamp is whatever point came at-or-before it,
// not whichever recorded point happens to be nearest in raw time. Across a big data gap,
// ECharts' own per-series nearest-neighbor axis-trigger snapping picks whichever side is
// closer, which can silently pick the *next* point instead — computing this ourselves from
// the series' own data, independent of ECharts' snap, is what makes it always correct.
function pointAtOrBefore(points: GraphPoint[], atMs: number): GraphPoint | undefined {
  let result: GraphPoint | undefined;
  for (const point of points) {
    const pointMs = new Date(point.at).getTime();
    if (pointMs <= atMs && (!result || pointMs > new Date(result.at).getTime())) {
      result = point;
    }
  }
  return result;
}

function isLastPoint(points: GraphPoint[], point: GraphPoint): boolean {
  const pointMs = new Date(point.at).getTime();
  return !points.some((other) => new Date(other.at).getTime() > pointMs);
}

// Mirrors the linear interpolation used to draw the dashed projection line itself
// (`chartOption`'s `projection-*` series: anchored at the last real point, heading to
// `window.projected_end_percentage` at `window.end`), so a hover past the last real sample
// reports the same value the dashed line is visually showing at that point.
function projectedValueAt(last: GraphPoint, window: GraphWindow, atMs: number): number | null {
  if (window.projected_end_percentage === null) return null;
  const lastMs = new Date(last.at).getTime();
  const endMs = new Date(window.end).getTime();
  if (endMs <= lastMs) return null;
  const t = Math.min(1, Math.max(0, (atMs - lastMs) / (endMs - lastMs)));
  return last.percentage + (window.projected_end_percentage - last.percentage) * t;
}

export function activeNotesAt(notes: NoteRange[], atMs: number): NoteRange[] {
  return notes.filter((note) => {
    const startMs = new Date(note.start).getTime();
    const endMs = note.end ? new Date(note.end).getTime() : Infinity;
    return atMs >= startMs && atMs <= endMs;
  });
}

// Same window facts as `windowDetailLines`, but as one short " · "-joined line instead of
// several full sentences — used in the grouped hover tooltip where every metric of the same
// account/provider already gets its own line, so a multi-line block per metric would be a
// wall of mostly-repeated text.
function compactWindowDetail(item: GraphSeries, window: GraphWindow, now: Date): string {
  const stats = computeWindowStats(item.points, window, now);
  const endMs = new Date(window.end).getTime();
  const parts = [
    `resets ${new Date(window.end).toLocaleString()} (${formatDuration(Math.max(0, endMs - now.getTime()))})`,
    `peak ${stats.maximumPercentage.toFixed(0)}%`,
  ];
  if (stats.burnRatePerHour !== null) parts.push(`${stats.burnRatePerHour.toFixed(1)}%/h`);
  if (stats.perfectLanding) {
    parts.push("right on spot!");
  } else if (window.exhausted_from && stats.exhaustedAfterMs !== null && stats.blockedForMs !== null) {
    parts.push(`hit 100% after ${formatDuration(stats.exhaustedAfterMs)}`, `blocked ${formatDuration(stats.blockedForMs)}`);
  } else if (stats.remainingPercentageAtEnd !== null) {
    parts.push(`${stats.remainingPercentageAtEnd.toFixed(0)}% left at end`);
  } else if (stats.projectedRemainingPercentageAtEnd !== null) {
    parts.push(`${stats.projectedRemainingPercentageAtEnd.toFixed(0)}% would be left`);
  } else if (stats.projectedExhaustedAt !== null) {
    const exhaustedAt = new Date(stats.projectedExhaustedAt);
    parts.push(`~100% in ${formatDuration(Math.max(0, exhaustedAt.getTime() - now.getTime()))}`);
  }
  return parts.join(" · ");
}

interface SeriesRow {
  item: GraphSeries;
  valueLabel: string;
  detail: string;
}

// One unified hover tooltip driven purely by the hovered x-position (not by precisely
// targeting a line or a markArea box): every currently-displayed series' value at that
// timestamp, grouped by account+provider (one color-swatched header, one compact line per
// metric underneath) instead of repeating the account/provider label per metric — plus any
// active promo/notice notes appended once at the end.
export function axisTooltipHtml(
  seriesList: GraphSeries[],
  paramsList: { axisValue?: unknown }[],
  accountLabels: Record<string, string>,
  now: Date,
  notes: NoteRange[] = [],
): string {
  const axisEntry = paramsList.find((params) => typeof params.axisValue === "number");
  if (!axisEntry) return "";
  const atMs = axisEntry.axisValue as number;
  const rows: SeriesRow[] = [];
  for (const item of seriesList) {
    const held = pointAtOrBefore(item.points, atMs);
    if (!held) continue;
    const window = windowByPoint(item.windows, new Date(atMs).toISOString());
    let valueLabel: string;
    if (window?.current && atMs > new Date(held.at).getTime() && isLastPoint(item.points, held)) {
      const projected = projectedValueAt(held, window, atMs);
      valueLabel = projected !== null ? `~${projected.toFixed(1)}% (projected)` : `${held.percentage.toFixed(1)}%`;
    } else {
      valueLabel = `${held.percentage.toFixed(1)}%`;
    }
    rows.push({ item, valueLabel, detail: window ? compactWindowDetail(item, window, now) : "" });
  }
  if (!rows.length) return "";

  const groups = new Map<string, SeriesRow[]>();
  for (const row of rows) {
    const key = `${row.item.provider}::${accountLabelFor(row.item, accountLabels)}`;
    (groups.get(key) ?? groups.set(key, []).get(key)!).push(row);
  }
  const blocks = Array.from(groups.values()).map((groupRows) => {
    const firstItem = groupRows[0]!.item;
    const swatch = `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${firstItem.color};margin-right:4px;"></span>`;
    const groupHeader = `${swatch}<strong>${accountLabelFor(firstItem, accountLabels)} · ${firstItem.provider}</strong>`;
    const metricLines = groupRows.map((row) => {
      const base = `&nbsp;&nbsp;${row.item.metric_name}: ${row.valueLabel}`;
      return row.detail ? `${base} — ${row.detail}` : base;
    });
    return [groupHeader, ...metricLines].join("<br/>");
  });

  const header = `<strong>${new Date(atMs).toLocaleString()}</strong>`;
  const noteLines = activeNotesAt(notes, atMs).map((note) => noteTooltipHtml(note));
  return [header, ...noteLines, ...blocks].join("<br/>");
}

export interface ChartOptions {
  now?: Date;
  legendSelected?: Record<string, boolean>;
  start?: Date;
  end?: Date;
  animate?: boolean;
  accountLabels?: Record<string, string>;
  notes?: NoteRange[];
  showDataPoints?: boolean;
}

export function chartOption(
  series: GraphSeries[],
  dark: boolean,
  exhaustedColor: string,
  options: ChartOptions = {},
): EChartsOption {
  const now = options.now ?? new Date();
  const accountLabels = options.accountLabels ?? {};
  const notes = options.notes ?? [];
  const showDataPoints = options.showDataPoints ?? false;
  const rendered: SeriesOption[] = [];
  for (const item of series) {
    const name = seriesDisplayName(item, accountLabels);
    rendered.push({
      id: `${item.account_id}/${item.metric_key}/actual`,
      name,
      type: "line",
      step: "end",
      showSymbol: showDataPoints,
      symbolSize: 6,
      data: item.points.map((point) => [point.at, point.percentage]),
      lineStyle: { color: item.color, width: 2 },
      itemStyle: { color: item.color },
      markArea: {
        silent: false,
        data: item.windows.map((window, index) => [
          {
            xAxis: window.start,
            yAxis: 0,
            itemStyle: { color: item.color, opacity: 0.16, borderColor: item.color, borderWidth: 1 },
            windowIndex: index,
          },
          { xAxis: window.end, yAxis: window.maximum_percentage, windowIndex: index },
        ]),
      },
    });
    for (const [index, window] of item.windows.entries()) {
      if (window.current) {
        const windowStart = new Date(window.start).getTime();
        const windowEnd = new Date(window.end).getTime();
        const last = [...item.points]
          .reverse()
          .find((point) => {
            const at = new Date(point.at).getTime();
            return at >= windowStart && at <= windowEnd;
          });
        if (last && window.projected_end_percentage !== null) {
          rendered.push({
            id: `${item.account_id}/${item.metric_key}/projection-${index}`,
            name,
            type: "line",
            showSymbol: false,
            silent: true,
            data: [
              [last.at, last.percentage],
              [window.end, window.projected_end_percentage],
            ],
            lineStyle: { color: item.color, type: "dashed", width: 2 },
          });
        }
      }
      if (window.exhausted_from) {
        rendered.push({
          id: `${item.account_id}/${item.metric_key}/exhausted-${index}`,
          name,
          type: "line",
          data: [],
          silent: true,
          markArea: {
            data: [[
              { xAxis: window.exhausted_from, yAxis: 0, itemStyle: { color: exhaustedColor, opacity: 0.3 } },
              { xAxis: window.end, yAxis: 100 },
            ]],
          },
        });
      }
    }
  }
  rendered.push({
    id: "now-line",
    type: "line",
    data: [],
    silent: true,
    animation: false,
    markLine: {
      symbol: "none",
      silent: true,
      animation: false,
      lineStyle: { color: "#ef4444", type: "dashed", width: 1 },
      label: { show: false },
      data: [{ xAxis: now.toISOString() }],
    },
  });
  if (notes.length) {
    rendered.push({
      id: "notes-marker",
      name: "Notes",
      type: "line",
      data: [],
      silent: false,
      markArea: {
        itemStyle: { color: "#94a3b8", opacity: 0.25 },
        data: notes.map((note, index) => [
          { xAxis: note.start, yAxis: 97, noteIndex: index },
          { xAxis: note.end ?? now.toISOString(), yAxis: 100, noteIndex: index },
        ]),
      },
    });
  }
  return {
    backgroundColor: "transparent",
    animation: options.animate ?? true,
    textStyle: { color: dark ? "#e5e7eb" : "#1f2937" },
    tooltip: {
      trigger: "axis",
      confine: true,
      extraCssText: "max-width: 22rem; white-space: normal; max-height: 60vh; overflow-y: auto;",
      backgroundColor: dark ? "#1f2937" : "#ffffff",
      borderColor: dark ? "#374151" : "#e5e7eb",
      textStyle: { color: dark ? "#e5e7eb" : "#1f2937" },
      formatter: (raw: unknown) => (Array.isArray(raw) ? axisTooltipHtml(series, raw as { axisValue?: unknown }[], accountLabels, now, notes) : ""),
    },
    legend: {
      type: "scroll",
      textStyle: { color: dark ? "#e5e7eb" : "#1f2937" },
      selected: options.legendSelected,
    },
    grid: { left: 50, right: 28, top: 52, bottom: 48 },
    xAxis: {
      type: "time",
      min: options.start ? options.start.getTime() : undefined,
      max: options.end ? options.end.getTime() : undefined,
      axisLabel: { color: dark ? "#9ca3af" : "#4b5563" },
      axisLine: { lineStyle: { color: dark ? "#374151" : "#d1d5db" } },
      splitLine: { lineStyle: { color: dark ? "#1f2937" : "#e5e7eb" } },
      axisPointer: { show: true, type: "line" },
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 100,
      axisLabel: { formatter: "{value}%", color: dark ? "#9ca3af" : "#4b5563" },
      axisLine: { lineStyle: { color: dark ? "#374151" : "#d1d5db" } },
      splitLine: { lineStyle: { color: dark ? "#1f2937" : "#e5e7eb" } },
    },
    series: rendered,
  };
}
