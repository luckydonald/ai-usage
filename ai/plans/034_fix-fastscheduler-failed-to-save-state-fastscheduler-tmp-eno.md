# Fix: fastscheduler "Failed to save state" (`fastscheduler.tmp` ENOENT)

## Context

`ERROR [fastscheduler] Failed to save state: [Errno 2] No such file or directory: '.../fastscheduler.tmp' -> '.../fastscheduler.json'`

Root cause (verified):

- fastscheduler 0.2.1 (`storage/json_backend.py:58-61`) saves via a **fixed** temp name
  (`state_file.with_suffix(".tmp")`), then `temp_file.replace(state_file)`.
- `src/ai_usage/crawler.py:233-234` points every crawler at `paths.local / "fastscheduler.json"`.
- `ps` shows **two** `ai-usage up` processes (PIDs 52572 and 81115) sharing that file. One writer's
  `replace()` moves the `.tmp` away; the other's `replace()` then hits ENOENT.
- The `.json` stays intact, but two crawlers also double-crawl and race on the database.

## Approach

Add a single-instance guard that survives being killed.

- New module `src/ai_usage/instance_lock.py` (no `_` prefix, per the Python style guide) with a small
  context manager around `fcntl.flock(fd, LOCK_EX | LOCK_NB)` on `paths.local / "crawler.lock"`.
- **Kill-resilient:** the lock belongs to the open file descriptor in the kernel, not to the file's existence.
  SIGKILL, crash or power loss releases it, so a leftover `crawler.lock` never blocks the next start.
  - Do not use exists-checks or PID files as the lock.
  - Do not unlink the file on exit (avoids an unlink/recreate race).
  - The PID written inside is informational only, for the "already running" message.
- In `Crawler.run()` (`crawler.py`), acquire the lock before `ensure_states()` and the immediate crawl.
  If it is held, `self.report(...)` that another crawler (pid N) is running and return.
- Keep the shared `fastscheduler.json`, so persisted `next_run_at` is not lost.
- Style: fully typed, Python 3.14, explicit `# end if` / `# end with` / `# end def` / `# end class` block endings.

## Files

- `src/ai_usage/instance_lock.py` (new)
- `src/ai_usage/crawler.py` (use the lock in `run()`, near line 219)
- `tests/test_instance_lock.py` (new): second acquire on the same path fails while the first is held. It
  succeeds after the holder is closed. It also succeeds when a stale lock file is left behind (including a
  holder killed with SIGKILL in a subprocess). Use tmp paths and isolate HOME.

## Verification

- `uv run pytest` for the new and existing crawler tests.
- Run `ai-usage up` twice in a real tty (the user runs it): the second exits with "already running", and the
  ERROR no longer appears.
- `kill -9` the first, then start again: it starts cleanly despite the leftover lock file.
- Now: stop the stray duplicate `ai-usage up` (user's choice of PID 52572 or 81115).
- Optional follow-up: check why a restart leaves the old `up` alive (`scripts/run.sh` and the tmux `startup-mac` session).

## Commits (lplp style, active)

- Commit after each completed task, staging explicit paths only; message via `ai/git/pending-commit.md` and `-F`.
- Land in order: (1) `[backend] crawler: ai: Run: Added a kill-resilient single-instance lock module.` with its test, then
  (2) `[backend] crawler: ai: Run: Refused to start a second crawler on the same state file.`
- Fold any `ai: updated prompt` / `ai: save decision` / `ai: record memory` auto-commits into the preceding work commit with `--amend`.
- Co-author trailers per the session attribution reminder.

## Note

`/code-style md` matched no reference (only `py`, `ts`, `vue`, `yarn` exist), so this plan follows the Python guide for code
and plain Markdown.
