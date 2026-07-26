Repo /home/user/git/luckydonald/ai-usage is an ai-usage tracking tool with a GUI overlay showing per-service usage. Find where:
1. The overlay widget renders service name (e.g. "claude", "codex") as text/badge — need file:line.
2. Time window / metric labels (e.g. "5h", "week", "session" or similar rolling windows) are rendered — file:line.
3. Info panels showing a "deprecated name" badge/chip, plus crawler type and account/user info — file:line.
4. Any existing icon/asset system already in repo (icon mapping per service, svg/png assets, icon font, emoji usage) — file:line and how icons are stored/loaded.
5. Tooltip mechanism already used in the GUI (what widget toolkit is this - Qt/tkinter/web/webview?) — file:line examples of existing tooltips.

Report file:line references, relevant code snippets (short), and the GUI framework in use. Don't propose solutions, just report findings.