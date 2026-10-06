---
name: claude-usage-local-api
description: Read the user's current Claude usage (session, weekly, Opus) from the ClaudeUsage macOS app via a local HTTP API
---

# Claude Usage Local API

The ClaudeUsage macOS app exposes the user's current Claude usage as JSON over a local HTTP server. The server binds only to `127.0.0.1` and is opt-in (the user must enable it in Settings → General → Local API).

## Base URL

```
http://127.0.0.1:47291
```

The user can change the port in Settings; this document reflects the currently configured port.

## Endpoints

All endpoints: `GET`, JSON. Every successful response includes `lastUpdated` (ISO-8601, when the app last fetched data) and `source` (`"claudeCode"` or `"email"`).

### `GET /session` — current 5-hour session

```json
{
  "lastUpdated": "2026-04-28T10:14:22Z",
  "source": "claudeCode",
  "available": true,
  "percentUsed": 42.7,
  "percentRemaining": 57.3,
  "resetsAt": "2026-04-28T15:00:00Z",
  "resetsInSeconds": 17138
}
```

`resetsAt` and `resetsInSeconds` may be `null` if the app's reset string can't be parsed.

If the account has no such window — Claude did not report it, so the app does not measure it — this returns **404** instead of a fabricated zero:

```json
{
  "error": "window_unavailable",
  "message": "Claude did not report a 5-hour session window for this account",
  "available": false
}
```

### `GET /weekly` — 7-day rolling window (all models)

Same shape as `/session`, including `available` and the 404 `window_unavailable` case.

### `GET /opus` — Opus-specific weekly quota

Same shape as `/session`, including `available` and the 404 `window_unavailable` case. Shares the weekly reset.

### `GET /usage` — full cached usage object

Returns the complete `UsageData` object plus `lastUpdated` and `source`. Use this when you want every field in one call.

### `GET /health` — server status

```json
{
  "ok": true,
  "lastUpdated": "2026-04-28T10:14:22Z",
  "uptimeSeconds": 1234
}
```

`lastUpdated` may be `null` if the app hasn't fetched yet.

## Error responses

| Code | `error` | Meaning |
|------|---------|---------|
| 404  | `not_found` | Unknown path |
| 404  | `window_unavailable` | `/session`, `/weekly` or `/opus` on an account that has no such window |
| 405  | `method_not_allowed` | Non-GET method |
| 503  | `no_data` | App has no cached usage yet |

Error body shape: `{"error": "<code>", "message": "<human readable>"}`. The `window_unavailable` body additionally carries `"available": false`.

## Examples

```bash
# How much session quota is left?
curl -s http://127.0.0.1:47291/session | jq '.percentRemaining'

# Everything in one shot
curl -s http://127.0.0.1:47291/usage
```

## Notes for AI agents

- This API is read-only. There are no POST endpoints.
- The server does not trigger refreshes; it returns whatever the app last cached. Check `lastUpdated` if freshness matters.
- The app refreshes automatically every 1–5 minutes. If `lastUpdated` is older than a few minutes, the app may be backgrounded or unauthenticated.
- A 503 means the app is running but hasn't fetched yet (e.g., just launched). Retry shortly.
- A 404 `window_unavailable` is not an error to retry: the plan simply has no such window (a Free account has no 5-hour session window, an account without Opus access has no Opus quota). Check `available` before reading `percentUsed` / `percentRemaining`, and don't report "100% remaining" for a window that doesn't exist. Use `/usage` if you want to see which windows the account actually has.
