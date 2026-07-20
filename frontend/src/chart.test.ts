import { describe, expect, it } from "vitest";

import { axisTooltipHtml, chartOption, computeWindowStats, noteTooltipHtml, percentThroughWindow, pointTooltipHtml, seriesDisplayName, windowByPoint, windowTooltipHtml } from "./chart";
import type { GraphSeries, GraphWindow, NoteRange } from "./types";

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

describe("seriesDisplayName", () => {
  it("falls back to a truncated account id when no label is known", () => {
    expect(seriesDisplayName(series)).toBe("Five hours · app-server · account");
  });

  it("uses the resolved account label instead of the raw id when available", () => {
    expect(seriesDisplayName(series, { account: "person@example.com" })).toBe("Five hours · app-server · person@example.com");
  });
});

describe("chart rendering contract", () => {
  it("renders actual steps, projection, and a now-line (no reset-boundary line)", () => {
    const option = chartOption([series], false, "#6b7280");
    const rendered = option.series;
    expect(Array.isArray(rendered)).toBe(true);
    if (!Array.isArray(rendered)) throw new Error("chart series must be an array");
    expect(rendered).toHaveLength(3);
    expect(rendered[0]).toMatchObject({ type: "line", step: "end", showSymbol: false });
    expect(rendered[1]).toMatchObject({ id: "account/five-hours/projection-0" });
    expect(rendered.at(-1)).toMatchObject({ id: "now-line" });
    expect(rendered.some((item) => typeof item.id === "string" && item.id.includes("/reset-"))).toBe(false);
  });

  it("hides data-point symbols by default but shows them when showDataPoints is set", () => {
    const rendered = chartOption([series], false, "#6b7280", { showDataPoints: true }).series;
    if (!Array.isArray(rendered)) throw new Error("chart series must be an array");
    expect(rendered[0]).toMatchObject({ showSymbol: true });
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

  it("adds a notes marker series only when notes are present", () => {
    const withoutNotes = chartOption([series], false, "#6b7280");
    const rendered = withoutNotes.series;
    if (!Array.isArray(rendered)) throw new Error("chart series must be an array");
    expect(rendered.some((item) => item.id === "notes-marker")).toBe(false);

    const note: NoteRange = {
      service: "codex",
      account_id: "account",
      text: "+50% weekly limits promo through Aug 19",
      start: "2026-07-01T00:00:00Z",
      end: null,
    };
    const withNotes = chartOption([series], false, "#6b7280", { notes: [note] });
    const renderedWithNotes = withNotes.series;
    if (!Array.isArray(renderedWithNotes)) throw new Error("chart series must be an array");
    const marker = renderedWithNotes.find((item) => item.id === "notes-marker");
    expect(marker).toBeDefined();
  });
});

describe("noteTooltipHtml", () => {
  it("shows the note text and an open-ended range when still active", () => {
    const html = noteTooltipHtml({
      service: "codex",
      account_id: "account",
      text: "+50% weekly limits promo",
      start: "2026-07-01T00:00:00Z",
      end: null,
    });
    expect(html).toContain("+50% weekly limits promo");
    expect(html).toContain("now");
  });

  it("shows a closed range when the note has ended", () => {
    const html = noteTooltipHtml({
      service: "codex",
      account_id: "account",
      text: "+50% weekly limits promo",
      start: "2026-07-01T00:00:00Z",
      end: "2026-07-10T00:00:00Z",
    });
    expect(html).not.toContain(" → now");
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

  it("projects remaining headroom when the current window is on track to land under 100%", () => {
    const [openWindow] = series.windows;
    if (!openWindow) throw new Error("fixture must define a window");
    // fixture's projected_end_percentage is 90
    const stats = computeWindowStats(series.points, openWindow, new Date("2026-07-17T12:00:00Z"));
    expect(stats.projectedRemainingPercentageAtEnd).toBeCloseTo(10);
    expect(stats.projectedExhaustedAt).toBeNull();
  });

  it("projects an exhaustion ETA when the current window is on track to blow past 100%", () => {
    const overshooting: GraphWindow = {
      start: "2026-07-17T09:00:00Z",
      end: "2026-07-17T14:00:00Z",
      maximum_percentage: 40,
      exhausted_from: null,
      current: true,
      projected_end_percentage: 150,
    };
    const stats = computeWindowStats(series.points, overshooting, new Date("2026-07-17T12:00:00Z"));
    expect(stats.projectedRemainingPercentageAtEnd).toBeNull();
    expect(stats.projectedExhaustedAt).not.toBeNull();
    // burn rate is 40%/hour over the 1h elapsed (09:00->11:00 start, last point 11:00 at 40%... see fixture)
    expect(new Date(stats.projectedExhaustedAt!).getTime()).toBeGreaterThan(new Date("2026-07-17T11:00:00Z").getTime());
  });
});

describe("tooltip HTML", () => {
  it("includes the key facts for a hovered point", () => {
    const [window] = series.windows;
    if (!window) throw new Error("fixture must define a window");
    const [point] = series.points;
    if (!point) throw new Error("fixture must define a point");
    const html = pointTooltipHtml(series, point, window, { account: "person@example.com" });
    expect(html).toContain("Service: codex");
    expect(html).toContain("Provider: app-server");
    expect(html).toContain("person@example.com");
    expect(html).toContain("20.0%");
  });

  it("includes the key facts for a hovered max-block", () => {
    const [window] = series.windows;
    if (!window) throw new Error("fixture must define a window");
    const html = windowTooltipHtml(series, window, new Date("2026-07-17T12:00:00Z"), { account: "person@example.com" });
    expect(html).toContain("person@example.com");
    expect(html).toContain("app-server");
    expect(html).toContain("40.0%");
  });

  it("omits the account/metric header line when includeHeader is false", () => {
    const [window] = series.windows;
    if (!window) throw new Error("fixture must define a window");
    const html = windowTooltipHtml(series, window, new Date("2026-07-17T12:00:00Z"), { account: "person@example.com" }, false);
    expect(html).not.toContain("person@example.com");
    expect(html).not.toContain("<strong>");
    expect(html).toContain("40.0%");
  });

  it("tells you how much headroom is left when the projection lands under 100%", () => {
    const [window] = series.windows;
    if (!window) throw new Error("fixture must define a window");
    const html = windowTooltipHtml(series, window, new Date("2026-07-17T12:00:00Z"), {});
    expect(html).toContain("Projected to land at 90.0%");
    expect(html).toContain("10.0% of your limit would be left to use");
  });

  it("tells you the burn rate and exhaustion ETA when the projection overshoots 100%", () => {
    const overshooting: GraphWindow = {
      start: "2026-07-17T09:00:00Z",
      end: "2026-07-17T14:00:00Z",
      maximum_percentage: 40,
      exhausted_from: null,
      current: true,
      projected_end_percentage: 150,
    };
    const html = windowTooltipHtml(series, overshooting, new Date("2026-07-17T12:00:00Z"), {});
    expect(html).toContain("hit 100% around");
    expect(html).toContain("That's in");
  });
});

describe("axisTooltipHtml", () => {
  const other: GraphSeries = {
    ...series,
    account_id: "other-account",
    metric_key: "seven-days",
    metric_name: "Seven days",
    points: [{ at: "2026-07-17T10:00:00Z", percentage: 55, current: null, maximum: null }],
    windows: [],
  };
  const now = new Date("2026-07-17T12:00:00Z");
  const atMs = (iso: string) => new Date(iso).getTime();

  it("renders one shared header and one row per series held at that timestamp, merging each series' own window detail in", () => {
    const html = axisTooltipHtml([series, other], [{ axisValue: atMs("2026-07-17T10:00:00Z") }], {}, now);
    expect(html).toContain("7/17/2026");
    expect(html.match(/<strong>7\/17\/2026/g)?.length).toBe(1);
    expect(html).toContain("Five hours");
    expect(html).toContain("20.0%");
    expect(html).toContain("Peak usage: 40.0%"); // series' window detail folded into its own row
    expect(html).toContain("Seven days");
    expect(html).toContain("55.0%");
  });

  it("holds the step-line's last value across a gap instead of snapping to whichever point is nearest in raw time", () => {
    // Hovering a hair before the 11:00 sample (much closer to it in raw time than to the
    // 10:00 sample) must still report the 10:00 value — the step line hasn't moved yet.
    const html = axisTooltipHtml([series], [{ axisValue: atMs("2026-07-17T10:59:59Z") }], {}, now);
    expect(html).toContain("<strong>account · app-server · Five hours</strong>: 20.0%");
    expect(html).not.toContain("</strong>: 40.0%");
  });

  it("interpolates the projected value once past the last real sample, matching the dashed projection line", () => {
    // Window: current, ends 14:00, projected_end_percentage 90; last real sample 11:00 @ 40%.
    // Halfway (12:30, 1.5h of the remaining 3h) should read 40 + (90-40)*0.5 = 65%.
    const html = axisTooltipHtml([series], [{ axisValue: atMs("2026-07-17T12:30:00Z") }], {}, now);
    expect(html).toContain("~65.0% (projected)");
  });

  it("appends any active note once, not per series", () => {
    const note: NoteRange = {
      service: "codex",
      account_id: "account",
      text: "+50% weekly limits promo",
      start: "2026-07-01T00:00:00Z",
      end: null,
    };
    const html = axisTooltipHtml([series, other], [{ axisValue: atMs("2026-07-17T10:00:00Z") }], {}, now, [note]);
    expect(html.match(/\+50% weekly limits promo/g)?.length).toBe(1);
  });

  it("skips a series with no sample at-or-before the hovered timestamp", () => {
    const html = axisTooltipHtml([series], [{ axisValue: atMs("2026-07-17T09:00:00Z") }], {}, now);
    expect(html).toBe("");
  });

  it("returns an empty string when nothing in paramsList carries a usable axis value", () => {
    expect(axisTooltipHtml([series], [], {}, now)).toBe("");
    expect(axisTooltipHtml([series], [{ axisValue: undefined }], {}, now)).toBe("");
  });
});
