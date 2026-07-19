---
name: feedback-squash-cleanup-at-scale
description: "At 150-commit scale, fold auto-commits by chronological adjacency to the nearest real commit rather than precise slug/content matching"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: c903d647-174d-46f2-8c61-8cf39dc278f1
  modified: 2026-07-18T19:31:30.710Z
---

When squash-cleaning a large number of unpushed auto-commits (dozens to hundreds), don't try to precisely match each plan/prompt/decision commit to the "thematically correct" real commit it was actually about (e.g. matching a saved plan's slug to the specific implementation commit that plan led to). At scale this requires diff-level judgment per commit and doesn't finish in reasonable effort.

Instead use two mechanical rules, applied uniformly across the whole range:
1. Auto-commits **before** the first real code commit in the range fold **forward** into it (requires reordering the rebase-todo: move that pick line before the fixups it's absorbing — safe as long as the real commit's files don't overlap with the auto-commits' files, which is true for `ai/query.md`/`ai/plans/*`/`ai/output/agents/*`/`ai/memory/*` vs `src/`/`tests/`/`frontend/`).
2. Every other auto-commit folds **backward** into the nearest **preceding** real commit — this needs no reordering at all, since that's already their natural chronological position.

**Why:** Applied this on `ai-usage`'s `mane` branch: 150 unpushed commits, only 21 were real code commits, the rest were `ai: updated prompt`/`ai: save decision`/`ai: agent N results`/`ai: save plan`/`ai: Todo updated` noise (see [[feedback_todo_commits_are_auto_commits]]). Some plan commits (e.g. a "006_real-web-api-providers" plan saved twice) chronologically preceded an unrelated small real commit before the plan's actual implementation landed much later — under precise matching those saves belong with the later commit, but under the two mechanical rules above they fold into whatever real commit is immediately preceding, which is "good enough" and dramatically cheaper than manual per-commit judgment.

**How to apply:** Before running the interactive rebase, create a safety branch/tag pointing at the current tip (e.g. `git branch pre-squash-backup HEAD`) since this is a history rewrite — even though it's local/unpushed and therefore safe to rewrite, a backup ref costs nothing and makes recovery trivial if the rebase goes sideways. State this simplification explicitly to the user rather than silently picking it.
