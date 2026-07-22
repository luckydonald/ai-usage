Repo: /home/user/git/luckydonald/ai-usage (frontend Vue app, backend FastAPI/Python).

Find where the "current data" usage cards render text like "56.5% of your limit would be left to use" and "100.0% remaining at window end". Search frontend/src for these phrases or similar (grep for "remaining at window end", "left to use", "would be left", "window end"). Also find the projection logic that computes whether usage is trending to finish before or after the window ends (search for "projectedValueAt", "projected", "burn rate", "exhaust" in frontend/src/chart.ts and any component files).

Report:
1. Exact file(s) and line numbers containing these card text templates.
2. The full function(s) that compute the projection/remaining values feeding into this text (show the code).
3. Any existing logic that computes an "exhaustion date/time" (a projected date-time when usage would hit 100%) — search for "exhaust", "runOut", "deplet", "estimatedEnd", etc. If none exists, say so clearly.
4. The data shape available (GraphWindow / GraphPoint types in frontend/src/types.ts) — show relevant fields (current, maximum, reset_at, window end, points list) so I know what's available to compute a projected exhaustion date.

Do not write code — pure research/reporting.