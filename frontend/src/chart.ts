import type { EChartsOption, SeriesOption } from "echarts";

import type { GraphSeries } from "./types";

export function seriesDisplayName(item: GraphSeries): string {
  return `${item.metric_name} · ${item.account_id.slice(0, 8)}`;
}

export function seriesKey(item: GraphSeries): string {
  return `${item.account_id}::${item.metric_key}`;
}

export interface ChartOptions {
  now?: Date;
  legendSelected?: Record<string, boolean>;
  start?: Date;
  end?: Date;
}

export function chartOption(
  series: GraphSeries[],
  dark: boolean,
  exhaustedColor: string,
  options: ChartOptions = {},
): EChartsOption {
  const now = options.now ?? new Date();
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
        silent: true,
        data: item.windows.map((window) => [
          {
            xAxis: window.start,
            yAxis: 0,
            itemStyle: { color: item.color, opacity: 0.16, borderColor: item.color, borderWidth: 1 },
          },
          { xAxis: window.end, yAxis: window.maximum_percentage },
        ]),
      },
    });
    for (const [index, window] of item.windows.entries()) {
      if (window.current) {
        rendered.push({
          id: `${item.account_id}/${item.metric_key}/reset-${index}`,
          name,
          type: "line",
          showSymbol: false,
          silent: true,
          data: [
            [window.start, 100],
            [window.end, 100],
          ],
          lineStyle: { color: item.color, type: "dotted", opacity: 0.75 },
        });
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
    textStyle: { color: dark ? "#e5e7eb" : "#1f2937" },
    tooltip: { trigger: "axis" },
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
