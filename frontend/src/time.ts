export type TimePreset = "day" | "week" | "month" | "year" | "all";

export const presetLabels: Record<TimePreset, string> = {
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
  if (preset === "day") start.setTime(now.getTime() - 24 * 60 * 60 * 1000);
  if (preset === "week") start.setTime(now.getTime() - 7 * 24 * 60 * 60 * 1000);
  if (preset === "month") return [subtractCalendarMonth(now), end];
  if (preset === "year") start.setUTCFullYear(start.getUTCFullYear() - 1);
  if (preset === "all") start.setTime(0);
  return [start, end];
}

export const wideningOrder: TimePreset[] = ["day", "week", "month", "year", "all"];

