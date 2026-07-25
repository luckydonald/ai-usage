---
name: feedback-squash-cleanup-at-scale
description: "At 150-commit scale, fold auto-commits by chronological adjacency to the nearest real commit rather than precise slug/content matching"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: c903d647-174d-46f2-8c61-8cf39dc278f1
  modified: 2026-07-18T19:31:30.710Z
---
Squash-clean many unpushed auto-commits (dozens-hundreds): don't match each plan/prompt/decision commit to "correct" real commit it belong to (e.g. plan slug to specific implementation commit). Scale need diff-judgment per commit, no finish reasonable effort.

Use two mechanical rules instead, apply uniform whole range:
1. Auto-commits **before** first real code commit in range fold **forward** into it (need reorder rebase-todo: move pick line before fixups it absorb — safe since real commit's files don't overlap auto-commits' files, true for `ai/query.md`/`ai/plans/*`/`ai/output/agents/*`/`ai/memory/*` vs `src/`/`tests/`/`frontend/`).
2. Every other auto-commit folds **backward** into nearest **preceding** real commit — no reorder needed, already natural chronological spot.

**Why:** Applied on `ai-usage`'s `mane` branch: 150 unpushed commits, only 21 real code commits, rest `ai: updated prompt`/`ai: save decision`/`ai: agent N results`/`ai: save plan`/`ai: Todo updated` noise (see [[feedback_todo_commits_are_auto_commits]]). Some plan commits (e.g. "006_real-web-api-providers" plan saved twice) chronologically precede unrelated small real commit before plan's actual implementation land much later — precise matching say those saves belong with later commit, but two mechanical rules fold them into whatever real commit immediately precede, "good enough" and way cheaper than manual per-commit judgment.

**How to apply:** Before running interactive rebase, create safety branch/tag at current tip (e.g. `git branch pre-squash-backup HEAD`) — history rewrite, even local/unpushed and safe to rewrite, backup ref cost nothing, make recovery trivial if rebase go sideways. State this simplification explicit to user, don't silent pick.
