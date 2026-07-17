import { describe, expect, it } from "vitest";

import { rangeForPreset, subtractCalendarMonth } from "./time";

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
});

