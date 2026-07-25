---
name: feedback-verify-baseline-before-blaming-refactor
description: Diff test failures against pre-refactor baseline before treating them as regressions
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 4c8846d9-394d-4f75-9329-2410ae54eadc
  modified: 2026-07-24T06:34:14.639Z
---
Refactor spawn failing test, diff against `mane` (pre-refactor) baseline first. Don't fix tests failed before change.

**Why:** providers/ restructure hit 5 failing tests (icon collision, 4 in test_progress.py). Confirmed pre-exist on untouched `mane`. Left alone, skip chasing unrelated bugs.

**How to apply:** Any refactor/migration task, run full suite on base branch first. Only new failures count regression. Related: [[project_ai_usage_provider_add_wizard]]
