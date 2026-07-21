import { describe, expect, it } from "vitest";

import { customRange, formatDuration, formatRelative, paddedChartEnd, rangeForPreset, subtractCalendarMonth, toDateInputValue, wideningOrder } from "./time";
import type { GraphSeries } from "./types";

describe("calendar month range", () => {
  it("uses the same day in the preceding month", () => {
    const now = new Date("2026-07-17T12:00:00Z");
    expect(subtractCalendarMonth(now).toISOString()).toBe("2026-06-17T12:00:00.000Z");
  });

  it("clamps to a short month", () => {
    const now = new Date("2026-03-31T12:00:00Z");
    expect(subtractCalendarMonth(now).toISOString()).toBe("2026-02-28T12:00:00.000Z");
  });

  it("builds a rolling seven day range", () => {
    const now = new Date("2026-07-17T12:00:00Z");
    const [start, end] = rangeForPreset("week", now);
    expect(end.getTime() - start.getTime()).toBe(7 * 24 * 60 * 60 * 1000);
  });

  it("builds the new short-window ranges", () => {
    const now = new Date("2026-07-17T12:00:00Z");
    expect(rangeForPreset("auto", now)[0].getTime()).toBe(now.getTime() - 60 * 60 * 1000);
    expect(rangeForPreset("1h", now)[0].getTime()).toBe(now.getTime() - 60 * 60 * 1000);
    expect(rangeForPreset("3h", now)[0].getTime()).toBe(now.getTime() - 3 * 60 * 60 * 1000);
    expect(rangeForPreset("6h", now)[0].getTime()).toBe(now.getTime() - 6 * 60 * 60 * 1000);
    expect(rangeForPreset("12h", now)[0].getTime()).toBe(now.getTime() - 12 * 60 * 60 * 1000);
  });

  it("does not include auto in the widening cascade", () => {
    expect(wideningOrder).not.toContain("auto");
    expect(wideningOrder[0]).toBe("1h");
  });
});

describe("custom range", () => {
  it("includes both the start and end day in full", () => {
    const [start, end] = customRange("2026-07-01", "2026-07-03");
    expect(start.getFullYear()).toBe(2026);
    expect(start.getMonth()).toBe(6);
    expect(start.getDate()).toBe(1);
    expect(start.getHours()).toBe(0);
    expect(start.getMinutes()).toBe(0);
    expect(end.getDate()).toBe(3);
    expect(end.getHours()).toBe(23);
    expect(end.getMinutes()).toBe(59);
  });

  it("supports a single-day range", () => {
    const [start, end] = customRange("2026-07-01", "2026-07-01");
    expect(end.getTime() - start.getTime()).toBe(24 * 60 * 60 * 1000 - 1);
  });

  it("round-trips through toDateInputValue", () => {
    const date = new Date(2026, 6, 5);
    expect(toDateInputValue(date)).toBe("2026-07-05");
  });

  it("pads single-digit months and days", () => {
    const date = new Date(2026, 0, 9);
    expect(toDateInputValue(date)).toBe("2026-01-09");
  });
});

function seriesWithCurrentWindowEnd(end: string): GraphSeries {
  return {
    service: "codex",
    provider: "app-server",
    account_id: "account",
    metric_key: "five-hours",
    metric_name: "Five hours",
    color: "#f97316",
    points: [],
    windows: [{ start: "2026-07-17T09:00:00Z", end, maximum_percentage: 40, exhausted_from: null, current: true, projected_end_percentage: null }],
  };
}

function seriesWithClosedWindowEnd(end: string): GraphSeries {
  const [series] = [seriesWithCurrentWindowEnd(end)];
  return { ...series, windows: series.windows.map((window) => ({ ...window, current: false })) };
}

describe("paddedChartEnd", () => {
  const start = new Date("2026-07-17T09:00:00Z");
  const end = new Date("2026-07-17T10:00:00Z");

  it("pads by exactly 10% of the timeframe by default, ignoring windows entirely", () => {
    const series = [seriesWithCurrentWindowEnd("2026-07-17T13:00:00Z")];
    const padded = paddedChartEnd("1h", start, end, series);
    expect(padded.getTime() - end.getTime()).toBe((end.getTime() - start.getTime()) * 0.1);
  });

  it("pads out to the last still-open window's end when includeWindowEnds is on and that's further than 10%", () => {
    const series = [seriesWithCurrentWindowEnd("2026-07-17T13:00:00Z")];
    const padded = paddedChartEnd("1h", start, end, series, true);
    expect(padded.toISOString()).toBe("2026-07-17T13:00:00.000Z");
  });

  it("still pads by 10% when includeWindowEnds is on but no current window reaches further", () => {
    const padded = paddedChartEnd("1h", start, end, [], true);
    expect(padded.getTime() - end.getTime()).toBe((end.getTime() - start.getTime()) * 0.1);
  });

  it("never pads custom or all-time ranges, even with includeWindowEnds on", () => {
    const series = [seriesWithCurrentWindowEnd("2026-07-17T13:00:00Z")];
    expect(paddedChartEnd("custom", start, end, series, true).getTime()).toBe(end.getTime());
    expect(paddedChartEnd("all", start, end, series, true).getTime()).toBe(end.getTime());
  });

  it("ignores non-current windows even when includeWindowEnds is on", () => {
    const series = [seriesWithClosedWindowEnd("2026-07-17T13:00:00Z")];
    const padded = paddedChartEnd("1h", start, end, series, true);
    expect(padded.getTime() - end.getTime()).toBe((end.getTime() - start.getTime()) * 0.1);
  });
});

describe("formatDuration", () => {
  it("formats sub-minute durations", () => {
    expect(formatDuration(0)).toBe("<1m");
  });

  it("formats hours and minutes", () => {
    expect(formatDuration(150 * 60_000)).toBe("2h 30m");
  });

  it("formats days and hours", () => {
    expect(formatDuration(26 * 3_600_000)).toBe("1d 2h");
  });
});

describe("formatRelative", () => {
  const now = new Date("2026-07-17T12:00:00Z");

  it("formats a future time as 'in <duration>'", () => {
    expect(formatRelative(new Date("2026-07-17T14:30:00Z"), now)).toBe("in 2h 30m");
  });

  it("formats a past time as '<duration> ago'", () => {
    expect(formatRelative(new Date("2026-07-17T09:30:00Z"), now)).toBe("2h 30m ago");
  });

  it("formats a time within a minute as 'just now'", () => {
    expect(formatRelative(new Date("2026-07-17T12:00:30Z"), now)).toBe("just now");
  });
});

