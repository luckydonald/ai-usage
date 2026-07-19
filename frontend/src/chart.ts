import type { EChartsOption, SeriesOption } from "echarts";

import { formatDuration } from "./time";
import type { GraphPoint, GraphSeries, GraphWindow } from "./types";

export function seriesDisplayName(item: GraphSeries): string {
  return `${item.metric_name} · ${item.account_id.slice(0, 8)}`;
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

  return {
    maximumPercentage: window.maximum_percentage,
    burnRatePerHour,
    exhaustedAfterMs,
    blockedForMs,
    remainingPercentageAtEnd,
    perfectLanding,
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
    `Provider: ${item.service}`,
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
    ? [`<strong>${accountLabelFor(item, accountLabels)} · ${item.metric_name}</strong>`]
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
  }
  return lines.join("<br/>");
}

export interface ChartOptions {
  now?: Date;
  legendSelected?: Record<string, boolean>;
  start?: Date;
  end?: Date;
  animate?: boolean;
  accountLabels?: Record<string, string>;
}

export function chartOption(
  series: GraphSeries[],
  dark: boolean,
  exhaustedColor: string,
  options: ChartOptions = {},
): EChartsOption {
  const now = options.now ?? new Date();
  const accountLabels = options.accountLabels ?? {};
  const rendered: SeriesOption[] = [];
  for (const item of series) {
    const name = seriesDisplayName(item);
    rendered.push({
      id: `${item.account_id}/${item.metric_key}/actual`,
      name,
      type: "line",
      step: "end",
      showSymbol: false,
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
  return {
    backgroundColor: "transparent",
    animation: options.animate ?? true,
    textStyle: { color: dark ? "#e5e7eb" : "#1f2937" },
    tooltip: {
      trigger: "item",
      confine: true,
      formatter: (raw: unknown) => {
        const params = raw as {
          componentType: string;
          seriesName?: string;
          dataIndex?: number;
          data?: unknown;
        };
        const item = series.find((entry) => seriesDisplayName(entry) === params.seriesName);
        if (!item) return "";
        if (params.componentType === "markArea") {
          const data = params.data as [{ windowIndex: number }, unknown];
          const window = item.windows[data[0].windowIndex];
          if (!window) return "";
          return windowTooltipHtml(item, window, now, accountLabels);
        }
        if (params.componentType === "series" && Array.isArray(params.data) && params.data.length === 2) {
          const point = item.points[params.dataIndex ?? -1];
          if (!point) return "";
          const window = windowByPoint(item.windows, point.at);
          return pointTooltipHtml(item, point, window, accountLabels);
        }
        return "";
      },
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
      axisPointer: { show: true, type: "line" },
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 100,
      axisLabel: { formatter: "{value}%", color: dark ? "#9ca3af" : "#4b5563" },
    },
    series: rendered,
  };
}
