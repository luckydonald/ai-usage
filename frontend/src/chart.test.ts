import { describe, expect, it } from "vitest";

import { chartOption } from "./chart";
import type { GraphSeries } from "./types";

const series: GraphSeries = {
  service: "codex",
  provider: "app-server",
  account_id: "account",
  metric_key: "five-hours",
  metric_name: "Five hours",
  color: "#f97316",
  points: [
    { at: "2026-07-17T10:00:00Z", percentage: 20, current: null, maximum: null },
    { at: "2026-07-17T11:00:00Z", percentage: 40, current: null, maximum: null },
  ],
  windows: [{
    start: "2026-07-17T09:00:00Z",
    end: "2026-07-17T14:00:00Z",
    maximum_percentage: 40,
    exhausted_from: null,
    current: true,
    projected_end_percentage: 90,
  }],
};

describe("chart rendering contract", () => {
  it("renders actual steps, reset boundary, projection, and a now-line", () => {
    const option = chartOption([series], false, "#6b7280");
    const rendered = option.series;
    expect(Array.isArray(rendered)).toBe(true);
    if (!Array.isArray(rendered)) throw new Error("chart series must be an array");
    expect(rendered).toHaveLength(4);
    expect(rendered[0]).toMatchObject({ type: "line", step: "end" });
    expect(rendered[2]).toMatchObject({ id: "account/five-hours/projection-0" });
    expect(rendered.at(-1)).toMatchObject({ id: "now-line" });
  });

  it("groups the actual/reset/projection series for one account+metric under a single legend name", () => {
    const option = chartOption([series], false, "#6b7280");
    const rendered = option.series;
    if (!Array.isArray(rendered)) throw new Error("chart series must be an array");
    const named = rendered.filter((item) => item.id !== "now-line");
    const names = new Set(named.map((item) => item.name));
    expect(names.size).toBe(1);
  });

  it("anchors the projection line to the last point inside the current window", () => {
    const [originalWindow] = series.windows;
    if (!originalWindow) throw new Error("fixture must define a window");
    const withStalePoint: GraphSeries = {
      ...series,
      points: [
        { at: "2026-07-16T08:00:00Z", percentage: 99, current: null, maximum: null },
        { at: "2026-07-17T10:00:00Z", percentage: 20, current: null, maximum: null },
      ],
      windows: [{ ...originalWindow, start: "2026-07-17T09:00:00Z" }],
    };
    const option = chartOption([withStalePoint], false, "#6b7280");
    const rendered = option.series;
    if (!Array.isArray(rendered)) throw new Error("chart series must be an array");
    const projection = rendered.find((item) => item.id === "account/five-hours/projection-0");
    expect(projection).toBeDefined();
    expect((projection as { data: [string, number][] }).data[0]).toEqual(["2026-07-17T10:00:00Z", 20]);
  });

  it("fixes the x-axis to the requested range instead of the data extent", () => {
    const start = new Date("2026-07-17T00:00:00Z");
    const end = new Date("2026-07-17T03:00:00Z");
    const option = chartOption([series], false, "#6b7280", { start, end });
    expect(option.xAxis).toMatchObject({ min: start.getTime(), max: end.getTime() });
  });

  it("leaves the x-axis auto-scaling when no range is given", () => {
    const option = chartOption([series], false, "#6b7280");
    expect(option.xAxis).toMatchObject({ min: undefined, max: undefined });
  });
});
