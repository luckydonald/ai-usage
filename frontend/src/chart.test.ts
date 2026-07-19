import { describe, expect, it } from "vitest";

import { chartOption, computeWindowStats, percentThroughWindow, pointTooltipHtml, windowByPoint, windowTooltipHtml } from "./chart";
import type { GraphSeries, GraphWindow } from "./types";

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
  it("renders actual steps, projection, and a now-line (no reset-boundary line)", () => {
    const option = chartOption([series], false, "#6b7280");
    const rendered = option.series;
    expect(Array.isArray(rendered)).toBe(true);
    if (!Array.isArray(rendered)) throw new Error("chart series must be an array");
    expect(rendered).toHaveLength(3);
    expect(rendered[0]).toMatchObject({ type: "line", step: "end" });
    expect(rendered[1]).toMatchObject({ id: "account/five-hours/projection-0" });
    expect(rendered.at(-1)).toMatchObject({ id: "now-line" });
    expect(rendered.some((item) => typeof item.id === "string" && item.id.includes("/reset-"))).toBe(false);
  });

  it("defaults to animated, but honors an explicit animate:false", () => {
    expect(chartOption([series], false, "#6b7280").animation).toBe(true);
    expect(chartOption([series], false, "#6b7280", { animate: false }).animation).toBe(false);
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

describe("windowByPoint", () => {
  const [window] = series.windows;
  if (!window) throw new Error("fixture must define a window");

  it("finds the window containing a timestamp", () => {
    expect(windowByPoint(series.windows, "2026-07-17T10:00:00Z")).toBe(window);
  });

  it("returns undefined outside every window", () => {
    expect(windowByPoint(series.windows, "2020-01-01T00:00:00Z")).toBeUndefined();
  });
});

describe("percentThroughWindow", () => {
  it("computes progress based on the point's own timestamp", () => {
    const window: GraphWindow = {
      start: "2026-07-17T09:00:00Z",
      end: "2026-07-17T13:00:00Z",
      maximum_percentage: 40,
      exhausted_from: null,
      current: true,
      projected_end_percentage: null,
    };
    expect(percentThroughWindow("2026-07-17T11:00:00Z", window)).toBeCloseTo(50);
  });
});

describe("computeWindowStats", () => {
  const closedNeverExhausted: GraphWindow = {
    start: "2026-07-17T09:00:00Z",
    end: "2026-07-17T13:00:00Z",
    maximum_percentage: 70,
    exhausted_from: null,
    current: false,
    projected_end_percentage: null,
  };
  const exhausted: GraphWindow = {
    start: "2026-07-17T09:00:00Z",
    end: "2026-07-17T13:00:00Z",
    maximum_percentage: 100,
    exhausted_from: "2026-07-17T11:00:00Z",
    current: false,
    projected_end_percentage: null,
  };

  it("reports remaining percentage for a closed window that never hit 100%", () => {
    const stats = computeWindowStats(series.points, closedNeverExhausted, new Date("2026-07-17T14:00:00Z"));
    expect(stats.remainingPercentageAtEnd).toBeCloseTo(30);
    expect(stats.exhaustedAfterMs).toBeNull();
    expect(stats.perfectLanding).toBe(false);
  });

  it("reports exhausted-after and blocked-for durations for an exhausted window", () => {
    const stats = computeWindowStats(series.points, exhausted, new Date("2026-07-17T14:00:00Z"));
    expect(stats.exhaustedAfterMs).toBe(2 * 60 * 60 * 1000);
    expect(stats.blockedForMs).toBe(2 * 60 * 60 * 1000);
    expect(stats.remainingPercentageAtEnd).toBeNull();
  });

  it("detects a perfect landing when the last point lands right at 100% near window end", () => {
    const window: GraphWindow = {
      start: "2026-07-17T09:00:00Z",
      end: "2026-07-17T13:00:00Z",
      maximum_percentage: 100,
      exhausted_from: null,
      current: false,
      projected_end_percentage: null,
    };
    const points = [
      { at: "2026-07-17T12:50:00Z", percentage: 95, current: null, maximum: null },
      { at: "2026-07-17T12:58:00Z", percentage: 100, current: null, maximum: null },
    ];
    const stats = computeWindowStats(points, window, new Date("2026-07-17T13:00:00Z"));
    expect(stats.perfectLanding).toBe(true);
  });

  it("leaves remainingPercentageAtEnd null for a still-open, not-yet-exhausted window", () => {
    const [openWindow] = series.windows;
    if (!openWindow) throw new Error("fixture must define a window");
    const stats = computeWindowStats(series.points, openWindow, new Date("2026-07-17T12:00:00Z"));
    expect(stats.remainingPercentageAtEnd).toBeNull();
  });
});

describe("tooltip HTML", () => {
  it("includes the key facts for a hovered point", () => {
    const [window] = series.windows;
    if (!window) throw new Error("fixture must define a window");
    const [point] = series.points;
    if (!point) throw new Error("fixture must define a point");
    const html = pointTooltipHtml(series, point, window, { account: "person@example.com" });
    expect(html).toContain("codex");
    expect(html).toContain("person@example.com");
    expect(html).toContain("20.0%");
  });

  it("includes the key facts for a hovered max-block", () => {
    const [window] = series.windows;
    if (!window) throw new Error("fixture must define a window");
    const html = windowTooltipHtml(series, window, new Date("2026-07-17T12:00:00Z"), { account: "person@example.com" });
    expect(html).toContain("person@example.com");
    expect(html).toContain("40.0%");
  });
});
