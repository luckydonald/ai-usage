export type TimePreset = "auto" | "1h" | "3h" | "6h" | "12h" | "day" | "week" | "month" | "year" | "all";

export const presetLabels: Record<TimePreset, string> = {
  auto: "Auto",
  "1h": "1 hour",
  "3h": "3 hours",
  "6h": "6 hours",
  "12h": "12 hours",
  day: "24 hours",
  week: "7 days",
  month: "Since this day last month",
  year: "1 year",
  all: "All time",
};

export function subtractCalendarMonth(now: Date): Date {
  const result = new Date(now);
  const targetMonth = now.getUTCMonth() - 1;
  result.setUTCDate(1);
  result.setUTCMonth(targetMonth);
  const finalDay = new Date(Date.UTC(result.getUTCFullYear(), result.getUTCMonth() + 1, 0)).getUTCDate();
  result.setUTCDate(Math.min(now.getUTCDate(), finalDay));
  return result;
}

export function rangeForPreset(preset: TimePreset, now = new Date()): [Date, Date] {
  const end = new Date(now);
  const start = new Date(now);
  if (preset === "auto") start.setTime(now.getTime() - 60 * 60 * 1000);
  if (preset === "1h") start.setTime(now.getTime() - 60 * 60 * 1000);
  if (preset === "3h") start.setTime(now.getTime() - 3 * 60 * 60 * 1000);
  if (preset === "6h") start.setTime(now.getTime() - 6 * 60 * 60 * 1000);
  if (preset === "12h") start.setTime(now.getTime() - 12 * 60 * 60 * 1000);
  if (preset === "day") start.setTime(now.getTime() - 24 * 60 * 60 * 1000);
  if (preset === "week") start.setTime(now.getTime() - 7 * 24 * 60 * 60 * 1000);
  if (preset === "month") return [subtractCalendarMonth(now), end];
  if (preset === "year") start.setUTCFullYear(start.getUTCFullYear() - 1);
  if (preset === "all") start.setTime(0);
  return [start, end];
}

export const wideningOrder: TimePreset[] = ["1h", "3h", "6h", "12h", "day", "week", "month", "year", "all"];
