## Summary

### 1. Card text templates (exact locations)

File: `/home/user/git/luckydonald/ai-usage/frontend/src/chart.ts`

- **`windowDetailLines`** (full-tooltip/card lines), lines 135–157:
  - Line 149: `` `${stats.remainingPercentageAtEnd.toFixed(1)}% remaining at window end` ``
  - Line 151: `` `Projected to land at ${(100 - stats.projectedRemainingPercentageAtEnd).toFixed(1)}%`, `${stats.projectedRemainingPercentageAtEnd.toFixed(1)}% of your limit would be left to use` ``
  - Line 154: `` `At this rate, you'll hit 100% around ${relativeTimeSpan(exhaustedAt, now)}` ``

- **`compactWindowDetail`** (compact one-liner used in the grouped hover tooltip), lines 226–247, is the same facts condensed:
  - Line 239: `` `${stats.remainingPercentageAtEnd.toFixed(0)}% left at end` ``
  - Line 241: `` `${stats.projectedRemainingPercentageAtEnd.toFixed(0)}% would be left` ``
  - Line 244: `` `~100% in ${formatDuration(...)}` ``

These are consumed by `windowTooltipHtml` (line 159) and `axisTooltipHtml` (line 260), which are wired into the ECharts tooltip formatter in `chartOption` (line 438). Test fixtures confirming the exact strings: `/home/user/git/luckydonald/ai-usage/frontend/src/chart.test.ts:316` (`"10.0% of your limit would be left to use"`).

### 2. The projection/remaining computation feeding the text

`computeWindowStats` in `chart.ts:43-99` is the single source of all these numbers:

```ts
export function computeWindowStats(points: GraphPoint[], window: GraphWindow, now: Date): WindowStats {
  const start = new Date(window.start).getTime();
  const end = new Date(window.end).getTime();
  const inWindow = points
    .filter((point) => {
      const at = new Date(point.at).getTime();
      return at >= start && at <= end;
    })
    .sort((a, b) => new Date(a.at).getTime() - new Date(b.at).getTime());

  const exhaustedAfterMs = window.exhausted_from ? new Date(window.exhausted_from).getTime() - start : null;
  const blockedForMs = window.exhausted_from ? end - new Date(window.exhausted_from).getTime() : null;
  const remainingPercentageAtEnd =
    !window.current && !window.exhausted_from ? Math.max(0, 100 - window.maximum_percentage) : null;

  let burnRatePerHour: number | null = null;
  const last = inWindow.at(-1);
  if (last) {
    const relevantEndMs = window.exhausted_from ? new Date(window.exhausted_from).getTime() : new Date(last.at).getTime();
    const elapsedMs = relevantEndMs - start;
    if (elapsedMs > 0) {
      const value = window.exhausted_from ? 100 : window.maximum_percentage;
      burnRatePerHour = (value / elapsedMs) * (60 * 60 * 1000);
    }
  }

  let perfectLanding = false;
  if (inWindow.length >= 2 && Math.abs(last!.percentage - 100) <= PERFECT_LANDING_TOLERANCE_PERCENT) {
    const previous = inWindow.at(-2)!;
    const gapToPrevious = new Date(last!.at).getTime() - new Date(previous.at).getTime();
    const gapToWindowEnd = end - new Date(last!.at).getTime();
    perfectLanding = gapToPrevious <= PERFECT_LANDING_MAX_GAP_MS && gapToWindowEnd <= PERFECT_LANDING_MAX_GAP_MS;
  }

  let projectedRemainingPercentageAtEnd: number | null = null;
  let projectedExhaustedAt: string | null = null;
  if (window.current && !window.exhausted_from && window.projected_end_percentage !== null) {
    const projected = window.projected_end_percentage;
    if (projected < 100 - PERFECT_LANDING_TOLERANCE_PERCENT) {
      projectedRemainingPercentageAtEnd = 100 - projected;
    } else if (projected > 100 + PERFECT_LANDING_TOLERANCE_PERCENT && last && burnRatePerHour) {
      const hoursToExhaustion = (100 - last.percentage) / burnRatePerHour;
      projectedExhaustedAt = new Date(new Date(last.at).getTime() + hoursToExhaustion * 60 * 60 * 1000).toISOString();
    }
  }

  return {
    maximumPercentage: window.maximum_percentage,
    burnRatePerHour,
    exhaustedAfterMs,
    blockedForMs,
    remainingPercentageAtEnd,
    perfectLanding,
    projectedRemainingPercentageAtEnd,
    projectedExhaustedAt,
  };
}
```

Key point: `window.projected_end_percentage` is **not computed in the frontend** — it's a value provided by the backend/API on the `GraphWindow` object (see below). The frontend only branches on it (< 100 → remaining%, > 100 → derives an ETA using a locally-computed `burnRatePerHour`).

There's also `projectedValueAt` (`chart.ts:205-212`), used only to interpolate the dashed projection line / hover value between the last real point and `window.end`, mirroring the same linear interpolation the chart draws — not used for the card text itself.

### 3. Existing "exhaustion date/time" logic

Yes — it already exists, but only as a fallback branch inside `computeWindowStats`, not as a general-purpose function:

- **`projectedExhaustedAt`** (`WindowStats` field, `chart.ts:40`) — the projected date-time hitting 100%, computed at `chart.ts:83-86`:
  ```ts
  } else if (projected > 100 + PERFECT_LANDING_TOLERANCE_PERCENT && last && burnRatePerHour) {
    const hoursToExhaustion = (100 - last.percentage) / burnRatePerHour;
    projectedExhaustedAt = new Date(new Date(last.at).getTime() + hoursToExhaustion * 60 * 60 * 1000).toISOString();
  }
  ```
  This only fires when `window.projected_end_percentage` (backend-supplied) already indicates an overshoot past 100%+tolerance. It reuses the same `burnRatePerHour` computed above from `window.maximum_percentage` and elapsed time — a simple linear extrapolation, not a distinct/reusable "estimatedEnd" utility.

- Also present: **`exhausted_from`** on `GraphWindow` — this is a *realized* (already-happened) exhaustion timestamp from the backend, not a *projected* one. It drives `exhaustedAfterMs`/`blockedForMs` (`chart.ts:53-54`) and the "Hit 100% after…/Blocked for…" lines.

No separate/standalone `runOut`, `deplet*`, or `estimatedEnd` function exists anywhere in the repo — grep across `frontend/src` found nothing beyond the above. I did not check the backend (Python) since the request was scoped to frontend; let me know if you'd like that grepped too (e.g. `projected_end_percentage`'s computation source, which must live in the FastAPI backend since it's just consumed here).

### 4. Data shape available (`frontend/src/types.ts`)

```ts
export interface GraphPoint {
  at: string;
  percentage: number;
  current: number | null;
  maximum: number | null;
}

export interface GraphWindow {
  start: string;
  end: string;
  maximum_percentage: number;
  exhausted_from: string | null;
  current: boolean;
  projected_end_percentage: number | null;
}

export interface GraphSeries {
  service: string;
  provider: string;
  account_id: string;
  metric_key: string;
  metric_name: string;
  color: string;
  points: GraphPoint[];
  windows: GraphWindow[];
}
```

Plus the non-graph "latest" snapshot shape:
```ts
export interface LatestMetric {
  event_id: string;
  service: string;
  provider: string;
  account_id: string;
  metric_key: string;
  metric_name: string;
  observed_at: string;
  reset_at: string | null;
  percentage: number;
  current: number | null;
  maximum: number | null;
  unit: string | null;
}
```

So for computing your own projected exhaustion date you'd have available, per window: `start`/`end` (ISO timestamps), `maximum_percentage` (peak reached so far), `current` (bool, is this the active window), `exhausted_from` (already-happened 100%-hit timestamp, or null), and `projected_end_percentage` (backend's own end-of-window percentage projection, or null) — plus the full `points[]` list (`{ at, percentage, current, maximum }`) for the window to derive your own burn rate/regression if you want an independent projection rather than relying on the backend's `projected_end_percentage`.