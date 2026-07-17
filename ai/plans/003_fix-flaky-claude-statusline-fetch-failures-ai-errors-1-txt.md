# Fix flaky Claude statusline fetch failures (ai/errors/1.txt)

## Context

`ai/errors/1.txt` shows the crawler repeatedly failing to crawl the `claude/statusline` account (`72fc02a2-...`):

```
Failed crawling Claude /usage in 30.3s: Claude /usage did not become ready; use Claude once to refresh the status relay
Claude /usage: backing off crawl interval to 240 seconds after failure 2.
```

Root cause (confirmed by reading `src/ai_usage/providers/claude.py:106-146`): `ClaudeStatusProvider.fetch` only uses the relay file (populated by a Claude Code statusline hook, see `install_status_relay`) when it is fresher than `stale_seconds` (default 120s). The relay file is only refreshed while a real interactive Claude Code session is actively rendering its statusline — so anytime the crawler runs and no one has touched Claude in the last 2 minutes (the common case for an unattended background crawler), it falls through to `run_claude_usage`, which spawns the `claude` binary in a pexpect PTY, sends `/usage`, and waits up to 30s for `"Current session"` to appear. That path is unreliable outside a genuinely interactive terminal (confirmed separately: spawning `claude` from within a sandboxed/nested session hits `"Remote Control failed · disabled by your organization's policy"` and never renders `/usage` output) — it reliably times out after 30s and raises `ProviderError`, which the crawler logs as a hard failure and responds to by backing off the crawl interval (240s, then 480s, ...).

The bug is architectural, not transient: a provider whose only *reliable* data source (the relay file) requires recent interactive use is fundamentally mismatched with a periodic background crawler, and its fallback path is not dependable enough to be treated as a hard failure. The fix is to stop treating "relay is a bit stale" or "pexpect fallback failed" as fatal when we already have *some* known-good relay data — serve the last-known relay snapshot instead of erroring, and only hit the pexpect path (or raise) when we have nothing better.

## Change

Edit `ClaudeStatusProvider.fetch` in `src/ai_usage/providers/claude.py:106-146`:

1. Read the relay file once up front (if configured and it exists) and parse it into `relay_metrics`/`relay_age` regardless of staleness.
2. If `relay_age <= stale_seconds`, return the relay metrics immediately as before (no pexpect attempt — the common/happy path is unchanged).
3. Otherwise (relay missing, empty, or stale), only attempt the pexpect `run_claude_usage` fallback if the relay data is missing entirely or older than a new, larger `hard_stale_seconds` threshold (new `ConfigurationField`, default e.g. `3600`). This avoids paying the 30s pexpect timeout on every single crawl cycle once the relay is merely "kind of stale" (2 min – 1 hr) — in that window we already have reasonably fresh data and gain nothing from retrying a flaky spawn every cycle.
4. If the pexpect fallback is attempted and raises `ProviderError` (or returns no metrics), and we have `relay_metrics` (even stale), return those instead of propagating the error — stale-but-known data beats a hard crawl failure.
5. Only raise `ProviderError("Claude /usage did not become ready; use Claude once to refresh the status relay")` when there is no relay data at all (never populated) and the pexpect fallback also fails.

Net effect: the crawler stops erroring/backing off as long as the relay has ever produced one good snapshot; freshness degrades gracefully instead of failing hard.

## Files

- `src/ai_usage/providers/claude.py` — `ClaudeStatusProvider.configuration_fields` (add `hard_stale_seconds` field) and `ClaudeStatusProvider.fetch` (restructure as above). No changes needed to `run_claude_usage`, `parse_status_payload`, `parse_usage_output`, or the relay-install machinery — those are unaffected and already confirmed correct.

## Tests

Add cases to `tests/test_providers.py` (alongside existing `test_claude_status_line_payload` / `test_claude_usage_output`) covering `ClaudeStatusProvider.fetch` directly with a temp relay file:
- Fresh relay file (age < `stale_seconds`) → returns relay metrics, no pexpect call (monkeypatch/assert `run_claude_usage` not invoked).
- Stale relay file (`stale_seconds` < age < `hard_stale_seconds`) → returns relay metrics without invoking pexpect fallback.
- Hard-stale relay file (age > `hard_stale_seconds`) with pexpect fallback failing (monkeypatch `run_claude_usage` to raise) → still returns the stale relay metrics instead of raising.
- No relay file at all, pexpect fallback failing → raises `ProviderError` with the existing message (unchanged behavior for a never-configured relay).

## Verification

- `uv run pytest tests/test_providers.py -q` — new + existing tests pass.
- Manually: touch the existing relay file at `~/.ai-usage/local/relay/72fc02a2-....json` to an old mtime (`touch -d '2 hours ago' ...`), then run `uv run ai-usage fetch --account 72fc02a2-0e64-4cb4-89f9-e9e218a6ff07` and confirm it returns metrics from the stale relay file instead of hanging for 30s / erroring.
