---
name: reference-compact-summary-transcript-path
description: Post-/compact summary names the pre-compact transcript jsonl path - Read it for lost detail
metadata: 
  node_type: memory
  type: reference
  originSessionId: 4c8846d9-394d-4f75-9329-2410ae54eadc
  modified: 2026-07-24T06:34:21.786Z
---

Post-`/compact` summary messages name exact pre-compact transcript path (`~/.claude/projects/<proj>/<sessionId>.jsonl`); directly Readable for exact snippets/errors lost in summary.

**Why:** User asked whether pre-compact detail recoverable - confirmed yes, path always in summary text.

**How to apply:** If detail seems lost after compaction, check compact summary message for jsonl path and Read it directly instead of asking user to re-explain.
