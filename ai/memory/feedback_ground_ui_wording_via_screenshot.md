---
name: feedback_ground_ui_wording_via_screenshot
description: "When a UI change request's wording is ambiguous against the actual running app, screenshot the live dev instance instead of guessing from code/plan alone"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: c77b952d-3d3d-4f06-9630-bdd4829adc23
  modified: 2026-07-26T22:34:48.877Z
---

When a user's UI-change wording could map to more than one component (e.g. "the overlay", "that dot separator", "the toggle") and code-reading alone leaves it ambiguous, open the actual running dev instance and screenshot/inspect it before finalizing the plan — don't just pick the reading that seems most likely from source.

**Why:** During the icon-ify-dashboard work (ai-usage), the user's clarifying answer referenced a "dot separator" they thought was on the Sankey overlay, but it actually only existed on the chart legend/tooltip elsewhere — they said "I was looking at a stale version of the website." Taking a screenshot of the actual running app (found via `ss -tlnp` for the real dev port, not the first guessed port) resolved the ambiguity in one step instead of more back-and-forth.

**How to apply:** For ai-usage specifically, the real running dashboard was on port 4458 (process name `ai-usage`), not the first Vite-looking port found (5173 turned out to be an unrelated todo-tracker app on this machine) — verify which process/port actually belongs to the project before trusting a screenshot from it. After code changes, `npm run build` in `frontend/` + reload is enough to see them (static dist served by the backend); only a *backend* code change requires restarting the running process.

**Don't overuse this.** Browser screenshots (navigate + screenshot + zoom + console-read round trips) are expensive — each one burns real tool-call budget. Reach for a screenshot only when wording is genuinely ambiguous against code/plan and the ambiguity actually blocks a decision (as above), or once at the end to verify a finished change actually renders. Don't screenshot after every small edit, don't take multiple confirmatory screenshots of the same state, and don't use it as a substitute for reading the component code when the code alone already answers the question.
