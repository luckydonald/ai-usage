---
name: user-no-tty-environment
description: "This environment has no tty - interactive CLI/wizard work can't be manually exercised here"
metadata: 
  node_type: memory
  type: user
  originSessionId: 4c8846d9-394d-4f75-9329-2410ae54eadc
  modified: 2026-07-24T06:34:17.756Z
---

This environment has no tty available.

**Why:** Wizard/interactive-CLI work (`ai-usage provider add`) can't be manually exercised here - confirmed finishing provider-add wizard rewrite (commit d59697e), had to skip manual CLI exercise.

**How to apply:** When finishing interactive CLI features, state explicitly that manual/tty testing was skipped rather than claiming verified; ask user to test locally instead.
