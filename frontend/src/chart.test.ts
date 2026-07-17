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
  it("renders actual steps, reset boundary, and projection", () => {
    const option = chartOption([series], false, "#6b7280");
    const rendered = option.series;
    expect(Array.isArray(rendered)).toBe(true);
    if (!Array.isArray(rendered)) throw new Error("chart series must be an array");
    expect(rendered).toHaveLength(3);
    expect(rendered[0]).toMatchObject({ type: "line", step: "end" });
    expect(rendered[2]).toMatchObject({ id: "account/five-hours/projection-0" });
  });
});
