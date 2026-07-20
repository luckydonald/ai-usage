import type { EChartsOption, SeriesOption } from "echarts";

import { formatDuration } from "./time";
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

export function windowTooltipHtml(
  item: GraphSeries,
  window: GraphWindow,
  now: Date,
  accountLabels: Record<string, string>,
  includeHeader = true,
): string {
  const stats = computeWindowStats(item.points, window, now);
  const lines = includeHeader
    ? [`<strong>${accountLabelFor(item, accountLabels)} · ${item.provider} · ${item.metric_name}</strong>`]
    : [];
  lines.push(
    `${new Date(window.start).toLocaleString()} → ${new Date(window.end).toLocaleString()}`,
    `Peak usage: ${stats.maximumPercentage.toFixed(1)}%`,
  );
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
    const msUntilExhaustion = Math.max(0, exhaustedAt.getTime() - now.getTime());
    lines.push(`At this rate, you'll hit 100% around ${exhaustedAt.toLocaleString()}`, `That's in ${formatDuration(msUntilExhaustion)}`);
  }
  return lines.join("<br/>");
}

function pointRowHtml(
  item: GraphSeries,
  point: GraphPoint,
  window: GraphWindow | undefined,
  accountLabels: Record<string, string>,
): string {
  const label = `${accountLabelFor(item, accountLabels)} · ${item.provider} · ${item.metric_name}`;
  const lines = [`<strong>${label}</strong>: ${point.percentage.toFixed(1)}%`];
  if (window) {
    const remainingMs = new Date(window.end).getTime() - new Date(point.at).getTime();
    lines.push(`Window end: ${new Date(window.end).toLocaleString()} (${formatDuration(remainingMs)} away)`);
  }
  return lines.join("<br/>");
}

function projectionRowHtml(item: GraphSeries, percentage: number, accountLabels: Record<string, string>): string {
  const label = `${accountLabelFor(item, accountLabels)} · ${item.provider} · ${item.metric_name}`;
  return `<strong>${label}</strong>: ~${percentage.toFixed(1)}% (projected)`;
}

interface AxisTooltipParams {
  seriesId?: string;
  seriesName?: string;
  dataIndex?: number;
  data?: unknown;
}

export function axisTooltipHtml(
  seriesList: GraphSeries[],
  paramsList: AxisTooltipParams[],
  accountLabels: Record<string, string>,
): string {
  let header: string | undefined;
  const rows: string[] = [];
  const itemsWithActualRow = new Set<GraphSeries>();
  const projectionEntries: { item: GraphSeries; at: string; percentage: number }[] = [];
  for (const params of paramsList) {
    if (!Array.isArray(params.data) || params.data.length !== 2) continue;
    const item = seriesList.find((entry) => seriesDisplayName(entry, accountLabels) === params.seriesName);
    if (!item) continue;
    if (params.seriesId?.endsWith("/actual")) {
      const point = item.points[params.dataIndex ?? -1];
      if (!point) continue;
      if (!header) header = `<strong>${new Date(point.at).toLocaleString()}</strong>`;
      itemsWithActualRow.add(item);
      const window = windowByPoint(item.windows, point.at);
      rows.push(pointRowHtml(item, point, window, accountLabels));
    } else if (params.seriesId?.includes("/projection-")) {
      // Beyond the last real sample, only the dashed projection line has any data at all —
      // without this, hovering purely in the future showed no tooltip whatsoever.
      const [at, percentage] = params.data as [string, number];
      projectionEntries.push({ item, at, percentage });
    }
  }
  for (const entry of projectionEntries) {
    if (itemsWithActualRow.has(entry.item)) continue;
    if (!header) header = `<strong>${new Date(entry.at).toLocaleString()}</strong>`;
    rows.push(projectionRowHtml(entry.item, entry.percentage, accountLabels));
  }
  return header ? [header, ...rows].join("<br/>") : "";
}

export function noteTooltipHtml(note: NoteRange): string {
  const start = new Date(note.start).toLocaleDateString();
  const range = note.end ? `${start} → ${new Date(note.end).toLocaleDateString()}` : `${start} → now`;
  return [`<strong>${note.text}</strong>`, range].join("<br/>");
}

export interface MarkAreaHoverEvent {
  seriesName?: string;
  data?: unknown;
}

// Under `tooltip.trigger: "axis"`, ECharts' own tooltip no longer auto-shows for markArea
// hover (window backgrounds, notes bands) — it's superseded by the axis-trigger slice
// everywhere. This renders the same region-detail content for a manually-wired
// mouseover/mouseout listener (see UsageChart.vue) that bypasses the built-in tooltip.
export function regionTooltipHtml(
  seriesList: GraphSeries[],
  event: MarkAreaHoverEvent,
  now: Date,
  accountLabels: Record<string, string>,
  notes: NoteRange[],
): string {
  if (!event.data || typeof event.data !== "object") return "";
  const data = event.data as { noteIndex?: number; windowIndex?: number };
  if (data.noteIndex !== undefined) {
    const note = notes[data.noteIndex];
    return note ? noteTooltipHtml(note) : "";
  }
  const item = seriesList.find((entry) => seriesDisplayName(entry, accountLabels) === event.seriesName);
  if (!item) return "";
  if (data.windowIndex === undefined) return "";
  const window = item.windows[data.windowIndex];
  if (!window) return "";
  return windowTooltipHtml(item, window, now, accountLabels);
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
      backgroundColor: dark ? "#1f2937" : "#ffffff",
      borderColor: dark ? "#374151" : "#e5e7eb",
      textStyle: { color: dark ? "#e5e7eb" : "#1f2937" },
      // Under axis-trigger, markArea hover (window backgrounds, notes bands) no longer
      // reaches this formatter at all — see UsageChart.vue's manual mouseover/mouseout
      // listener + regionTooltipHtml, which renders that content independently.
      formatter: (raw: unknown) => (Array.isArray(raw) ? axisTooltipHtml(series, raw as AxisTooltipParams[], accountLabels) : ""),
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
