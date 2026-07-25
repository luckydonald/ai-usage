---
name: user-no-tty-environment
description: "This environment has no tty - interactive CLI/wizard work can't be manually exercised here"
metadata: 
  node_type: memory
  type: user
  originSessionId: 4c8846d9-394d-4f75-9329-2410ae54eadc
  modified: 2026-07-24T06:34:17.756Z
---
No tty here. Wizard/interactive-CLI work (`ai-usage provider add`) can't test manual.

**Why:** Finish provider-add wizard rewrite (commit d59697e), skip manual CLI exercise.

**How to apply:** Finishing interactive CLI features — state manual/tty testing skipped, don't claim verified. Ask user test locally instead.
