import type { GraphSeries } from "./types";

export type TimePreset = "auto" | "1h" | "3h" | "6h" | "12h" | "day" | "week" | "month" | "year" | "all" | "custom";

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
  custom: "Custom range",
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

// Extends `end` into the future on relative ranges so a still-open window's projection/reset boundary
// stays visible, without ever pulling in future padding for "custom" or "all time" ranges.
export function paddedChartEnd(preset: TimePreset, start: Date, end: Date, series: GraphSeries[]): Date {
  if (preset === "custom" || preset === "all") return end;
  const duration = end.getTime() - start.getTime();
  const tenPercent = duration * 0.1;
  let lastCurrentWindowEnd: number | undefined;
  for (const item of series) {
    for (const window of item.windows) {
      if (!window.current) continue;
      const windowEnd = new Date(window.end).getTime();
      if (lastCurrentWindowEnd === undefined || windowEnd > lastCurrentWindowEnd) lastCurrentWindowEnd = windowEnd;
    }
  }
  const timeUntilLastWindowEnd = lastCurrentWindowEnd === undefined ? 0 : Math.max(0, lastCurrentWindowEnd - end.getTime());
  const padding = Math.max(tenPercent, timeUntilLastWindowEnd);
  return new Date(end.getTime() + padding);
}

const MS_PER_MINUTE = 60 * 1000;
const MS_PER_HOUR = 60 * MS_PER_MINUTE;
const MS_PER_DAY = 24 * MS_PER_HOUR;

// Picks the two largest non-zero units among days/hours/minutes, e.g. "2h 32m", "3d 4h", "<1m".
export function formatDuration(ms: number): string {
  const magnitude = Math.abs(ms);
  if (magnitude < MS_PER_MINUTE) return "<1m";
  const days = Math.floor(magnitude / MS_PER_DAY);
  const hours = Math.floor((magnitude % MS_PER_DAY) / MS_PER_HOUR);
  const minutes = Math.floor((magnitude % MS_PER_HOUR) / MS_PER_MINUTE);
  const sign = ms < 0 ? "-" : "";
  if (days > 0) return `${sign}${days}d ${hours}h`;
  if (hours > 0) return `${sign}${hours}h ${minutes}m`;
  return `${sign}${minutes}m`;
}

// Both dates are inclusive: `startText`'s whole day through `endText`'s whole day, in local time.
export function customRange(startText: string, endText: string): [Date, Date] {
  return [new Date(`${startText}T00:00:00`), new Date(`${endText}T23:59:59.999`)];
}

export function toDateInputValue(date: Date): string {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}
