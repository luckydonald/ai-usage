---
name: feedback-todo-commits-are-auto-commits
description: "\"[todo]\"/\"ai: Todo added/updated/cleared\" commits are auto-commit noise like the documented lplp patterns, even though the commit-with-lplp-style skill doesn't list them explicitly"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: c903d647-174d-46f2-8c61-8cf39dc278f1
  modified: 2026-07-18T19:31:14.826Z
---

This repo's `commit-with-lplp-style` skill documents these auto-commit hook patterns to fold away during cleanup: `ai: updated prompt`, `ai: save decision <slug>`, `ai: agent <id> results`, `ai: record memory <slug>`, and plan commits (`ai: save plan <NNN>_<slug>` / `ai: Plan …`). In practice this repo also has a TaskCreate/TaskUpdate-driven hook producing `[todo] <text>.` and `ai: Todo added`/`ai: Todo updated`/`ai: Todo cleared` commits (touching `ai/plans/pending.md` or a plan file) every time the todo/task list changes — these are NOT in the skill's documented list but behave identically: single-file, tool-generated, zero standalone value, and should be folded the same way (into the nearest real code commit) during a squash-cleanup.

**Why:** Discovered while doing a full squash-cleanup of 150 unpushed commits on `mane` — roughly 130 of them were auto-commit noise, and `ai: Todo updated` alone accounted for a large fraction. Treating it as "not a known pattern" would have left it un-folded and defeated the point of the cleanup.

**How to apply:** [[feedback_squash_cleanup_at_scale]] — when auditing a branch for stray auto-commits (via the lplp skill or manually), always check `git log` for single-file commits touching `ai/plans/pending.md`, `ai/query.md`, `ai/output/agents/*`, or `ai/memory/*` even if the commit message doesn't literally match one of the skill's listed patterns — the "single file, tool-generated, no real code" shape is the actual signal, not the exact wording.
