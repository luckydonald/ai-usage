# Real web-API providers for Claude/Codex/Copilot usage

## Context

App already ships an `experimental` generic stub, `PrivateWebProvider` (`src/ai_usage/providers/web.py`), subclassed as `ClaudeWebProvider`/`CodexWebProvider`/`CopilotEntitlementsProvider`. It only extracts one arbitrary percentage field via cookie/header replay against a user-configured endpoint — no real per-service parsing, no multi-window/reset support. User wants real, production-quality providers hitting the actual known endpoints:

- Claude: `https://claude.ai/api/organizations/{uuid}/usage` (page `claude.ai/new#settings/usage`) — both Team and Personal org variants.
- Codex: `https://chatgpt.com/backend-api/wham/usage` (page `chatgpt.com/codex/settings/usage`).
- Copilot: `https://github.com/github-copilot/chat/entitlement` (page `github.com/settings/copilot/features`).
- Plus: Codex CLI `/status` weekly-limit bar scraping — **this already exists**, `CodexStatusProvider` in `codex.py` (pexpect-driven, regex `STATUS_PATTERN`), registered as `codex/cli-status`. Pattern already matches the "Weekly limit: [████░] 63% left (resets 12:36 on 24 Jul)" format described — no new work needed here beyond a quick confirmation.

Actual JSON response shapes for the three web endpoints are unknown until captured live, so this plan starts with a browser debug session before writing any parsing code.

## Part 1 — Capture real response shapes (browser session)

User logs into each site beforehand; use `claude-in-chrome` MCP tools (`navigate`, `javascript_tool`/`read_network_requests`) to hit the endpoint while authenticated and capture:
- Full JSON response body (redact/note any org UUID or account-identifying values before pasting into code/tests).
- Whether Claude's endpoint differs between a Team org and a Personal org (two captures needed for Claude).
- Response headers relevant to auth (pure cookie-based, or does it also need a bearer/CSRF header alongside cookies?).

**Order**: Claude first (per user's choice — resolve Team-vs-Personal org variance up front since it's likely to affect provider config shape), then Codex, then Copilot.

## Part 2 — Implement real providers

Replace each `PrivateWebProvider` subclass with a dedicated provider class (keep `PrivateWebProvider` itself only if still useful as a fallback/experimental catch-all — otherwise remove it once real providers exist). Follow the existing production idioms already in the codebase rather than inventing new ones:

- **Multi-window percentage metrics** (Claude/Codex style) — mirror `claude.py: parse_status_payload()` and `codex.py: parse_rate_limits()`: parse each window (e.g. five-hour/weekly) into its own `Metric(usage=Usage(percentage=...), reset_at=..., window_seconds=...)`.
- **Quota-count metrics** (Copilot style, if entitlement reports counts not percentages) — mirror `copilot.py: CopilotBillingProvider.fetch()`: `MinMaxUsage(current=..., maximum=..., unit=...)`.
- Each new provider's `fetch()` takes `account: AccountConfig` + `credential: dict` (cookies/headers/org-uuid as needed), same shape as the current stub; org UUID for Claude becomes a required `configuration_fields` entry (`ConfigurationField(key="org_id", ...)`) so Team-vs-Personal is just "which org UUID is configured," not separate code paths — confirm this is workable once Part 1's capture confirms the two org types hit the same endpoint shape.
- Register the new providers in `registry.py: built_in_registry()` in place of (or alongside, if kept experimental) the current `web.py` entries.
- Raise `ProviderError` on non-200 / schema-shape mismatches, matching current stub behavior.

## Part 3 — Tests

New `respx`-mocked tests in `tests/test_providers.py`, following the existing `test_copilot_billing_provider` pattern: mock the real endpoint URL, return a JSON fixture built from Part 1's captured shape (with fake/anonymized values), assert the resulting `Metric`s (key/name/percentage or current/maximum/reset_at/window_seconds) match expectations. One test per provider at minimum; add a second Claude test if Team vs Personal genuinely differ in parsing.

## Part 4 — Codex CLI stale-warning triggers a 10s recrawl

Codex's `/status` output sometimes includes:
```
Warning:              limits may be stale - run /status again shortly.
```
`CodexStatusProvider`/`parse_codex_status()`/`STATUS_PATTERN` (`src/ai_usage/providers/codex.py`) currently don't look for this line at all. When present, the crawler should recrawl this account in 10s instead of the normal interval.

- `models.py: FetchStatus` already has an unused `STALE` value (currently dead — not referenced anywhere). Reuse it: `parse_codex_status()`/`CodexStatusProvider.fetch()` detects the `"Warning:"` / `"limits may be stale"` substring in the raw pexpect output and sets `ProviderFetchResult(status=FetchStatus.STALE, ...)` (metrics still populated as normal — the run itself succeeded, it's just telling us to check again soon).
- `crawler.py: Crawler.update_state()` (87-147): add a `FetchStatus.STALE` branch before/alongside the existing `FetchStatus.ERROR` branch (100-111) that sets `state.next_run_at = now + timedelta(seconds=10)` and skips the normal active/normal-interval computation. 10s can be a plain constant (e.g. `STALE_RECHECK_SECONDS = 10`) near the other interval defaults in `config.py`, not necessarily a new configurable field, unless reuse elsewhere is expected.
- No new fields needed on `ProviderFetchResult` — `status` alone carries the signal, matching how `ERROR` already works.

## Verification

- `uv run pytest -q` — new provider tests green, no regressions in the existing suite.
- Manual: configure a real account via `ai-usage provider add` pointing at each new provider, run a fetch, confirm metrics land in the dashboard with sensible percentages/reset times.
