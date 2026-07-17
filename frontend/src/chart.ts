import type { EChartsOption, SeriesOption } from "echarts";

import type { GraphSeries } from "./types";

export function chartOption(series: GraphSeries[], dark: boolean, exhaustedColor: string): EChartsOption {
  const rendered: SeriesOption[] = [];
  for (const item of series) {
    rendered.push({
      id: `${item.account_id}/${item.metric_key}/actual`,
      name: `${item.metric_name} · ${item.account_id.slice(0, 8)}`,
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
          type: "line",
          showSymbol: false,
          silent: true,
          data: [
            [window.start, 100],
            [window.end, 100],
          ],
          lineStyle: { color: item.color, type: "dotted", opacity: 0.75 },
        });
        const last = item.points.at(-1);
        if (last && window.projected_end_percentage !== null) {
          rendered.push({
            id: `${item.account_id}/${item.metric_key}/projection-${index}`,
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
  return {
    backgroundColor: "transparent",
    textStyle: { color: dark ? "#e5e7eb" : "#1f2937" },
    tooltip: { trigger: "axis" },
    legend: { type: "scroll", textStyle: { color: dark ? "#e5e7eb" : "#1f2937" } },
    grid: { left: 50, right: 28, top: 52, bottom: 48 },
    xAxis: { type: "time", axisLabel: { color: dark ? "#9ca3af" : "#4b5563" } },
    yAxis: {
      type: "value",
      min: 0,
      max: 100,
      axisLabel: { formatter: "{value}%", color: dark ? "#9ca3af" : "#4b5563" },
    },
    series: rendered,
  };
}

