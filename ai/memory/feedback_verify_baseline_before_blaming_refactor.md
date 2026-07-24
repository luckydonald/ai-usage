---
name: feedback-verify-baseline-before-blaming-refactor
description: Diff test failures against pre-refactor baseline before treating them as regressions
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 4c8846d9-394d-4f75-9329-2410ae54eadc
  modified: 2026-07-24T06:34:14.639Z
---

When refactor introduces failing tests, diff against `mane` (pre-refactor) baseline before treating any failure as a regression - don't fix tests that already failed before the change.

**Why:** During providers/ restructure, hit 5 failing tests (icon collision, 4 in test_progress.py); confirmed all pre-existed on untouched `mane`, so left them alone instead of chasing unrelated bugs.

**How to apply:** Any refactor/migration task - run full suite on base branch first, treat only new failures as regressions. Related: [[project_ai_usage_provider_add_wizard]]
