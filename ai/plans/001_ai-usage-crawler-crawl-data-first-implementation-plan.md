# AI Usage Crawler — Crawl-Data-First Implementation Plan

## Summary

Build a local-first, modular usage crawler with a Python 3.14 backend/CLI and a bundled Vue 3 dashboard. Deliver the complete specification incrementally in this order:

1. **Collect data ASAP:** provider framework, encrypted local state, Git-mergeable history, working Codex and Claude collectors, `add`, `fetch`, and `crawl`.
2. **Make data useful:** FastAPI query API and Vue graphs.
3. **Complete collection:** Copilot, alternate CLI providers, private web APIs, credential discovery/import, browser-cookie and interactive-login flows.
4. **Complete operations:** `serve`, `run-all`, detach mode, Linux systemd and macOS launchd installation.
5. **Finish portability:** Windows collection, credential import, browser support, and startup integration.

Use `src/ai_usage`, `alembic`, and `frontend` as the three primary implementation areas.

## Core Architecture and Public Contracts

- Define Pydantic discriminated models:
  - `Usage(kind="percentage", percentage: float)`.
  - `MinMaxUsage(kind="min_max", current: float, maximum: float, unit: str, percentage: float)`.
  - `Metric(key, name, usage, observed_at, reset_at, window_seconds, metadata)`.
  - `ProviderFetchResult(account_id, provider, metrics, fetched_at, status, error)`.
  - Percentages are normalized to `0..100`; provider-native current/max values remain available.
- Define an async provider interface with `discover()`, `configuration_fields()`, `authenticate()`, and `fetch()`. Load built-ins and third-party providers through Python entry points so adding a service requires no crawler/API changes.
- Declare provider configuration fields once and use them to generate:
  - Dynamic `ai-usage add <service> <provider> --foo=value` options.
  - Textual-based interactive forms for missing values.
  - Pydantic validation and YAML serialization.
  - A non-interactive mode that fails with a list of missing flags.
- Store account definitions in `~/.ai-usage/services/<service>/<account-id>.yml`. Account IDs are stable UUIDs with separate editable display names, allowing multiple accounts for the same provider.
- Use async SQLAlchemy 2.x with fully typed `Mapped[...]` models, `async_sessionmaker`, SQLite/`aiosqlite`, and Alembic async migrations. Automatically upgrade under a process lock before commands access the database; also expose `ai-usage db upgrade`.
- The chmod-0600, gitignored local SQLite database stores credentials, fetch runs, source identity, file-index state, and the rebuildable query index.
  - Encrypt credential values with AES-256-GCM and per-value nonces.
  - Key precedence: `AI_USAGE_CREDENTIAL_KEY`, then `AI_USAGE_CREDENTIAL_KEY_FILE`, then an atomically generated chmod-0600 `~/.ai-usage/credential.key`.
  - The key is never stored in SQLite. Environment injection makes the design container-ready, but container manifests are not part of this implementation.
- Write canonical metric samples to mergeable daily JSONL files:
  - `history/v1/<service>/<account>/<metric>/<year>/<month>/<day>/<source-id>.jsonl`.
  - Each machine has a local, unsynced source ID, preventing normal cross-machine append conflicts.
  - Deterministic event IDs and a SQLite uniqueness constraint make re-indexing and merged duplicates harmless.
  - Index files incrementally by byte offset; rebuild a changed/truncated file and record malformed lines without rewriting synced history.
- Git compatibility covers configuration/history file merging only; the application does not automatically commit, pull, or push.

## Providers, Crawling, and Commands

- First usable providers:
  - **Codex `app-server`:** start `codex app-server --stdio`, initialize JSON-RPC, reuse or materialize the configured account profile, call `account/read` and `account/rateLimits/read`, and map primary/secondary windows by duration. The documented response supplies `usedPercent`, duration, and reset time, and the same interface supports managed browser/device login. [OpenAI Codex app-server documentation](https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md)
  - **Claude `statusline`:** install a relay that ingests the documented `rate_limits.five_hour` and `rate_limits.seven_day` data while preserving and forwarding to any existing status-line command. Scope each relay to its configured Claude profile/account and restore the previous command only when the wrapper is still owned by `ai-usage`.
  - If no relay sample newer than two minutes exists, use a PTY to run `/usage`, strip terminal control sequences, and parse the 5-hour, weekly, and model-specific sections. Timeouts or incompatible CLI output become visible provider errors rather than stale values. [Claude status-line schema](https://code.claude.com/docs/en/statusline)
- Remaining providers:
  - Codex `cli-status`, invoking `/status` twice before parsing the second result.
  - Claude standalone `cli-usage` and experimental private web usage provider.
  - Copilot personal AI-credit provider using GitHub’s versioned billing API and a fine-grained token with `Plan: read`. Require configured allowance and billing-cycle anchor when the API does not return a maximum/reset; support organization endpoints as a separate admin provider. [GitHub billing usage API](https://docs.github.com/en/rest/billing/usage)
  - Copilot experimental entitlement provider using the IDE/client private quota surface for remaining-percentage data.
  - A Copilot CLI parser remains capability-disabled until the CLI exposes usage output.
- Implement reusable credential sources for filesystem/profile discovery, native CLI/device login, interactive browser login, and Chrome/Chromium, Firefox, and Safari cookie extraction.
  - Import only target-domain credentials after explicit confirmation.
  - Store imported values encrypted in SQLite.
  - Materialize temporary chmod-0700 CLI profiles when a client requires files, re-import refreshed credentials transactionally, and remove temporary profiles after use.
  - Mark private API and cookie providers `experimental`, isolate their schemas/parsers, and fail with an upgrade-oriented diagnostic when upstream responses change.
- `ai-usage add` performs service-specific discovery and offers existing Codex, Claude, Copilot, and GitHub profiles as import candidates. It never silently imports credentials.
- `ai-usage fetch` loads all configured accounts concurrently with per-account locks, persists each successful metric independently, reports partial failures, and exits non-zero only if every selected account fails.
- `ai-usage crawl` uses FastScheduler with these defaults:
  - Normal interval: 10 minutes.
  - Active interval: 1 minute for 15 minutes after a positive usage increase.
  - Reset/decrease does not count as activity; schedule a fetch shortly after a known reset.
  - Retry failures with exponential backoff and jitter, capped at one hour.
  - Resolve settings from global → service → provider → configured account, with the most specific value winning.
  - Persist next-run/error state so restarts remain observable without putting scheduler state in Git history. [FastScheduler package](https://pypi.org/project/fastscheduler/)
- Complete CLI behavior:
  - `serve --host localhost --port 4458`.
  - `run-all` runs crawler and server in one asyncio process.
  - Bare `ai-usage` aliases `run-all`.
  - `crawl`, `run-all`, and applicable install flows support `-d/--detach`, PID metadata, graceful shutdown, and logs under local state.
  - `install` mirrors crawler flags, asks `--serve/--no-serve`, accepts server flags when enabled, and installs a user-level service.
  - Linux uses systemd user units; macOS uses launchd agents; Windows startup support is the final platform phase.
  - `uninstall`/`deinstall` removes only owned service files and leaves accounts, credentials, and history intact.

## API, Dashboard, Graphs, and Monitoring

- FastAPI serves the built Vue/Vite SPA and typed read-only endpoints:
  - `GET /api/v1/catalog` for services, providers, accounts, metrics, colors, and availability.
  - `GET /api/v1/latest` for current cards/status.
  - `GET /api/v1/series` with service/provider/account/metric filters and explicit start/end.
  - `GET /api/v1/events` as SSE for newly indexed samples and provider state.
  - `GET /api/v1/health`.
- Binding to a non-loopback address remains unauthenticated by user choice, but prints a prominent startup/log warning and shows an exposure warning in the dashboard.
- Compute graph windows in the backend so UI and tests share one algorithm:
  - Group samples by metric and reset window; use `reset_at - window_seconds` when known, otherwise the first active observation.
  - Render actual usage as a staircase line on a `0..100%` axis.
  - Render each reset window with a 50%-opacity fill, full-opacity border, and height equal to the window maximum.
  - For a current window, extend the time axis to its future reset, draw a dotted 100% reset box, and project a dotted diagonal from the latest value using average observed consumption rate. Omit projection without a positive elapsed delta and clamp it to 100%.
  - From the first 100% sample until reset, shade the exhausted region using the configured exhausted color, default gray.
- Vue uses Vue 3, strict TypeScript, `<script setup lang="ts">`, SCSS, Vue Router, and Apache ECharts custom/step series.
  - Hierarchical multi-select filters cover service, provider, configured account, and metric.
  - Color precedence is account metric override → provider default → service default → generated palette.
  - Presets are 24 hours, 7 days, “same day last month” (for July 17, begin June 17, clamped for short months), rolling year, and all time.
  - Default to 24 hours and automatically widen through those presets until data is found.
  - Support system dark mode plus a persisted manual override.
- Add opt-in direct Sentry integration for both applications:
  - Separate `SENTRY_DSN` and `VITE_SENTRY_DSN`, environment/release/build tags, no default PII, and tracing disabled unless configured.
  - Initialize Python monitoring before FastAPI creation and explicitly capture lifespan failures.
  - Upload frontend sourcemaps only when build-time credentials exist, then remove distributable map files.
  - Provide clearly marked, environment-gated backend/frontend sample-error routes.
  - Do not implement a Sentry/Bugsink tunnel at this stage; browser delivery requires a directly reachable DSN.

## Test and Acceptance Plan

- Backend tests with pytest, pytest-asyncio, Hypothesis, HTTPX, and mocked HTTP transports:
  - Pydantic validation, normalization, account/config precedence, encryption round trips, wrong-key failures, file permissions, and secret redaction.
  - Alembic upgrade from an empty database, upgrade across every revision, and protection of credential rows during index rebuilds.
  - Concurrent JSONL append, cross-source merge, duplicate indexing, truncation/re-indexing, malformed lines, and timezone/reset boundaries.
  - Fixture-driven Codex JSON-RPC, Codex status, Claude status-line, Claude PTY, GitHub REST, and private-provider parsers without real accounts.
  - Fake-clock crawler tests for normal/active intervals, cooldown, reset scheduling, retry backoff, cancellation, and partial failure.
  - FastAPI contract, filtering, SSE, static SPA delivery, non-loopback warning, and Sentry-disabled startup.
- Frontend tests with Vitest, Vue Test Utils, and mocked API/SSE:
  - Catalog/filter behavior, preset calculations including short months, empty/error/stale states, color precedence, dark-mode persistence, and accessibility labels.
  - ECharts option generation for staircase data, maximum boxes, current-window projection, dotted reset box, and exhausted shading.
- Playwright end-to-end tests:
  - Load seeded multi-service history, change every filter level, switch time presets and themes, receive a live SSE update, and verify graph/card changes.
  - Exercise both backend and frontend sample-error routes when explicitly enabled.
- Platform tests:
  - Golden/dry-run tests for systemd, launchd, detach/PID behavior, idempotent install/uninstall, paths containing spaces, missing CLIs, and unavailable credential stores.
  - Windows equivalents are added with the final platform phase.
- Milestone acceptance:
  - Phase 1 is complete when real Codex and Claude accounts can produce mergeable samples through `fetch` and adaptive `crawl`.
  - Phase 2 is complete when those samples render correctly through the API and dashboard.
  - Phase 3 is complete when Copilot and every specified authentication/import strategy have fixture coverage and at least one real smoke test per service.
  - Final completion requires Linux/macOS startup verification, Windows support, all backend/frontend suites passing, and no credentials appearing in YAML, JSONL, API responses, logs, or Sentry events.

## Assumptions

- Linux and macOS are first-class initially; Windows is required but implemented last.
- Private web APIs are supported as explicitly experimental adapters because their schemas are not stable public contracts.
- The SQLite database and encryption key are always local and gitignored; only YAML configuration and JSONL history are intended for Git merging.
- No Docker image/Compose files and no Sentry tunnel are included, although the credential-key environment contract is container-ready.
- The dashboard intentionally has no authentication, including on non-loopback bindings; warnings document that exposure.
