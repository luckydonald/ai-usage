---
name: feedback-todo-commits-are-auto-commits
description: "\"[todo]\"/\"ai: Todo added/updated/cleared\" commits are auto-commit noise like the documented lplp patterns, even though the commit-with-lplp-style skill doesn't list them explicitly"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: c903d647-174d-46f2-8c61-8cf39dc278f1
  modified: 2026-07-18T19:31:14.826Z
---
This repo's `commit-with-lplp-style` skill list auto-commit hook patterns to fold during cleanup: `ai: updated prompt`, `ai: save decision <slug>`, `ai: agent <id> results`, `ai: record memory <slug>`, plan commits (`ai: save plan <NNN>_<slug>` / `ai: Plan …`). Repo also got TaskCreate/TaskUpdate-driven hook making `[todo] <text>.` and `ai: Todo added`/`ai: Todo updated`/`ai: Todo cleared` commits (touch `ai/plans/pending.md` or plan file) every todo/task list change — not in skill's list but behave same: single-file, tool-generated, zero standalone value. Fold same way (into nearest real code commit) during squash-cleanup.

**Why:** Found during full squash-cleanup of 150 unpushed commits on `mane` — ~130 auto-commit noise, `ai: Todo updated` alone big chunk. Treat as "unknown pattern" would leave un-folded, defeat cleanup point.

**How to apply:** [[feedback_squash_cleanup_at_scale]] — auditing branch for stray auto-commits (lplp skill or manual), always check `git log` for single-file commits touching `ai/plans/pending.md`, `ai/query.md`, `ai/output/agents/*`, or `ai/memory/*` even if message don't match skill's listed patterns exact — "single file, tool-generated, no real code" shape real signal, not exact wording.
