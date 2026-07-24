Task: extract memory candidates from transcript. Done reading.

Candidates (not already covered):

**feedback: verify-baseline-before-blaming-refactor**
Rule: When refactor introduces failing tests, diff against `mane` (pre-refactor) baseline before treating any failure as a regression — don't try to fix tests that already failed before the change.
Why: During providers/ restructure, hit 5 failing tests (icon collision in one, 4 in test_progress.py); confirmed all pre-existed on `mane` untouched, so left them alone instead of chasing unrelated bugs.
How to apply: Any refactor/migration task — run full suite on base branch first, treat only new failures as regressions.

**user: no-tty-environment**
Fact: This environment has no tty available for the user.
Why: Wizard/interactive-CLI work (`ai-usage provider add`) can't be manually exercised here — confirmed when finishing the provider-add wizard rewrite (commit `d59697e`), had to skip manual CLI exercise.
How to apply: When finishing interactive CLI features, state explicitly that manual/tty testing was skipped rather than claiming it was verified; ask user to test locally instead.

**reference: compact-summary-has-transcript-path**
Fact: Post-`/compact` summary messages name the exact pre-compact transcript path (`~/.claude/projects/<proj>/<sessionId>.jsonl`); it's directly Readable for exact snippets/errors lost in the summary.
Why: User asked whether pre-compact detail was recoverable — confirmed yes, path is always in the summary text.
How to apply: If detail seems lost after compaction, check the compact summary message for the jsonl path and Read it directly instead of asking user to re-explain.

Skipped: login/usage mock-target and provider-add wizard notes — already in existing memory files (`feedback_login_usage_split_test_targets.md`, `project_ai_usage_provider_add_wizard.md`).