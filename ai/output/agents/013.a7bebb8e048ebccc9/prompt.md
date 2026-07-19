Repo: ai-usage (local-first CLI/dashboard usage tracker for Claude/Codex/Copilot), at /home/user/git/luckydonald/ai-usage.

I need to plan bugfixes + new hover-tooltip features for its usage graphs (likely a web dashboard with line charts showing usage % over time windows, refreshed periodically e.g. every 10s).

Find and report (very thorough):
1. Where the frontend graph/chart code lives (JS/TS/HTML, whatever framework — could be vanilla JS, Chart.js, D3, etc). File paths.
2. How the graph currently refreshes/redraws periodically — is there polling every ~10s? Does the whole chart get destroyed/recreated each refresh, or just data updated? This relates to a bug: "it still refreshes completely every 10 or so seconds, causing another left-to-right-graph-draw animation. That animation is only allowed on page load / the initial draw of a line. After that it's forbidden!"
3. How "max-block" / max-growth-box is drawn (a highlighted region on the chart) — relates to bug: "At the top of the graph (100%) there's a stray line whenever there's a max-growth-box being displayed. Remove the line."
4. Any existing hover/tooltip code for chart points, and what data is available per-datapoint (timestamp, provider, account, percentage, window end time, etc) — relates to feature request to add rich hover tooltips for both individual measurement points AND max-blocks (with burn-rate calc, 100%-reached detection, etc).
5. How time-range / relative timeframe selection works, and how far into the future the graph currently extends (relates to: "On all relative time ranges, the graph should always display max(10% of selected timeframe, last closing of a window still running) into the future").
6. Any existing type/data model for a single usage measurement and for a "window"/limit block (start/end time, percentage, provider, account) — file paths and shape.

Report file paths and relevant code snippets/line numbers. Do not propose fixes — just report what exists so a plan can be written against real code.