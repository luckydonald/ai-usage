# AI Usage

AI Usage is a local-first dashboard and crawler for AI coding-service limits. It collects usage from Codex, Claude, and GitHub Copilot, keeps a merge-friendly history, and shows how each allowance is being consumed over time.

Everything runs on your machine. Account configuration and history live in `~/.ai-usage`; credentials are encrypted and kept out of the files intended for Git sync.

## What you get

- Multiple accounts and collection methods per service.
- One-shot collection or an adaptive background crawler.
- A responsive Vue dashboard with light and dark themes.
- Filters for service, provider, account, metric, and time range.
- Stepped usage lines, reset-window overlays, projections, and exhausted periods.
- JSON API and live Server-Sent Events updates.
- User-level startup installation on Linux, macOS, and Windows.
- Optional direct Sentry or Bugsink reporting for backend and frontend errors.

## Requirements

- Python 3.14 or newer.
- The corresponding service CLI for CLI-backed collection: `codex` and/or `claude`.
- Node.js and Corepack only when building the dashboard from source.

## Install from source

Build the frontend, then install the Python application:

```shell
cd frontend
corepack yarn@4.9.2 install
corepack yarn@4.9.2 build
cd ..
uv tool install .
```

For development, use `uv sync --extra test` instead of `uv tool install .` and run commands as `uv run ai-usage ...`.

## Quick start: Codex and Claude

Discover local accounts that can be imported:

```shell
ai-usage provider discover
ai-usage provider discover codex app-server
ai-usage provider discover claude statusline
```

Running `ai-usage provider add` in a terminal opens a selection screen containing discovered accounts, followed by a separate “Manually configure other…” menu. To configure the local Codex and Claude profiles non-interactively:

```shell
ai-usage provider add codex app-server \
  --profile-dir "$HOME/.codex" \
  --no-input

ai-usage provider add claude statusline \
  --no-input
```

The Claude command uses Claude Code's native default profile. Add `--profile-dir /path/to/profile` only for an alternate Claude profile. The status-line collector installs a composable relay in that profile. If a status-line command already exists, AI Usage preserves it and forwards the same input to it. When the relay is missing or stale, the collector falls back to running `claude /usage` in a pseudo-terminal.

Fetch one sample from every configured account:

```shell
ai-usage fetch
```

Then start the crawler and dashboard together:

```shell
ai-usage up
```

Open <http://localhost:4458>. Running `ai-usage` without a subcommand prints a short status summary and the command list.

## Add GitHub Copilot

The recommended collector reuses the OAuth token the Copilot CLI already stores in `~/.copilot/config.json` (or `COPILOT_GITHUB_TOKEN`/`GH_TOKEN`/`GITHUB_TOKEN`) to read premium-request quota — no extra token to create or store:

```shell
ai-usage provider add copilot statusline --no-input
```

Alternatively, the billing-API collector reads monthly AI-credit usage from GitHub's billing API. Put a suitable GitHub token in a private JSON file so it does not appear in shell history:

```json
{"token": "github_pat_..."}
```

Then configure the account:

```shell
ai-usage provider add copilot github-api \
  --username octocat \
  --allowance 300 \
  --billing-day 1 \
  --secret-file ./github-credential.json \
  --no-input
```

Delete the plaintext credential file after confirming `ai-usage fetch` works. AI Usage stores an encrypted copy in its local SQLite database.

## Commands

| Command | Purpose |
| --- | --- |
| `ai-usage provider discover [SERVICE] [PROVIDER]` | Inspect importable local accounts across all matching collectors; this is read-only. |
| `ai-usage provider add [SERVICE] [PROVIDER]` | Select a discovered account or manually configure a collector. Alias: `new`. |
| `ai-usage provider list [SERVICE] [PROVIDER]` | List active, disabled, and soft-removed accounts. Alias: `ls`. |
| `ai-usage provider status [SERVICE] [PROVIDER] [ACCOUNT]` | Show stored configuration, latest usage, fetch result, and crawl state. Alias: `info`. |
| `ai-usage provider remove [SERVICE] [PROVIDER] [ACCOUNT]` | Disable an account and remove its local secrets while preserving history. Aliases: `del`, `rm`. |
| `ai-usage fetch [--account ID]` | Collect one sample now. Repeat `--account` to limit the run. |
| `ai-usage crawl [-d]` | Run the adaptive collector loop, optionally detached. |
| `ai-usage serve [--host HOST] [--port PORT]` | Serve the dashboard and API without crawling. |
| `ai-usage up [-d]` (alias `start`) | Crawl and serve together. |
| `ai-usage install [--serve/--no-serve]` | Install and start a user-level startup service. |
| `ai-usage uninstall` / `deinstall` | Remove the startup service without deleting data. |
| `ai-usage completion [--shell ...]` | Install shell completion for Bash, Zsh, or Fish. |
| `ai-usage db-upgrade` | Apply pending Alembic migrations manually. |

Use `ai-usage provider COMMAND --help` for provider-management options. Provider-specific fields can be supplied as regular flags, such as `--profile-dir`, `--command`, or `--allowance`.

### Remove or restore an account

Removing an account is a soft deletion by default:

```shell
ai-usage provider remove --account ACCOUNT_ID
```

The account YAML remains with `enabled: false` and a `removed_at` timestamp, so the state and usage history can synchronize through Git. AI Usage immediately deletes the machine-local encrypted credential, crawl state, fetch-run state, and Claude relay integration. Repeating the command is safe.

When the same local account is discovered and added again, AI Usage restores its existing ID and history. To permanently remove both the tombstone and its JSONL history, use the explicit destructive flag:

```shell
ai-usage provider rm --account ACCOUNT_ID --delete-history --no-input
```

Interactive removal asks whether the history should also be deleted and defaults to preserving it.

## Collection methods

| Service | Provider | Status | Notes |
| --- | --- | --- | --- |
| Codex | `app-server` | Recommended | Reads current rate limits through the local Codex app server. |
| Codex | `cli-status` | Supported | Parses `codex /status`; invokes it twice to refresh stale output. |
| Claude | `statusline` | Recommended | Uses the lightweight status relay and falls back to `claude /usage`. |
| Claude | `cli-usage` | Supported | Always parses `claude /usage` in a pseudo-terminal. |
| Copilot | `statusline` | Recommended | Reuses the Copilot CLI's own local token to read premium-request quota; no separate token needed. |
| Copilot | `github-api` | Supported | Reads GitHub AI-credit billing usage with an encrypted token. |
| Codex/Claude | `web` | Experimental | Generic private JSON endpoint adapter; private APIs may change without notice. |
| Copilot | `entitlements` | Experimental | Generic private entitlement endpoint adapter. |

Third-party packages can register additional collectors through the `ai_usage.providers` Python entry-point group. A provider implements the `Provider` interface and returns typed `Metric` values.

## Dashboard and graph

The graph uses percentage consumed, from 0% to 100%:

- Solid staircase lines are observed samples.
- Translucent boxes summarize the highest usage in each reset window.
- Dotted lines project the current window from its observed consumption rate.
- Dotted reset boxes extend active windows into the future.
- Gray shading marks the part of a window after an allowance reached 100%.

Choose 24 hours, 7 days, the same calendar day last month, 1 year, or all history. On first load the dashboard automatically widens the range until it finds samples.

Metric colors can be set in an account YAML file:

```yaml
colors:
  five-hours: "#d97706"
  seven-days: "#ea580c"
```

## Crawl intervals

The normal interval is 10 minutes. When consumption increases, that account switches to a 1-minute interval for 15 minutes. Failed requests use exponential backoff up to one hour. A small random jitter prevents every account from fetching at exactly the same time.

Override the global defaults in `~/.ai-usage/config.yml`:

```yaml
intervals:
  normal_seconds: 600
  active_seconds: 60
  active_for_seconds: 900
  maximum_backoff_seconds: 3600

services:
  claude:
    intervals:
      normal_seconds: 300

providers:
  app-server:
    intervals:
      active_seconds: 90
```

An account's own `intervals` mapping has the highest priority, followed by provider, service, and global settings.

## Data, sync, and credentials

The default layout is:

```text
~/.ai-usage/
├── config.yml
├── services/<service>/<account-id>.yml
├── history/<service>/<account-id>/<date>.jsonl
├── credential.key
└── local/
    ├── state.sqlite3
    └── logs/
```

The YAML configuration and daily JSONL history are stable, append-oriented files suitable for Git. Event IDs make histories mergeable. `local/`, the rebuildable SQLite index, logs, and `credential.key` are ignored by the generated `.gitignore`.

Credentials are encrypted with AES-GCM before storage in SQLite. By default AI Usage generates a mode-`0600` key at `~/.ai-usage/credential.key`. For managed deployments, set either `AI_USAGE_CREDENTIAL_KEY` to a URL-safe base64 32-byte key or `AI_USAGE_CREDENTIAL_KEY_FILE` to a protected key file. Credential material is intentionally not synchronized with the history.

Set `AI_USAGE_HOME` to move the entire data directory.

## Running in the background

Install a startup service with the dashboard enabled:

```shell
ai-usage install --serve --host localhost --port 4458
```

Use `--no-serve` for collection only. The installer uses a systemd user unit on Linux, a LaunchAgent on macOS, and a logon task on Windows. `ai-usage uninstall` removes only that integration and keeps all account and history data.

Detached runs are also available without installing a startup service:

```shell
ai-usage up --detach
```

Their output is written beneath `~/.ai-usage/local/logs/`.

## Security

The web server has no authentication. Its default `localhost` binding is intentional. If you bind to `0.0.0.0` or another non-loopback address, the CLI and dashboard warn that anyone able to reach the port can read the usage data. Put an authenticating reverse proxy in front of it before exposing it to a network.

The private-web providers are experimental and accept cookie/header credentials. Prefer the stable CLI-backed collectors, and never commit plaintext secret files or the local credential key.

## Sentry or Bugsink

Backend and frontend reporting are independent and connect directly to their DSNs; no tunnel is required.

Copy the relevant values from `.env.example`:

- Backend: `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_RELEASE`, `SENTRY_TRACES_SAMPLE_RATE`.
- Frontend: `VITE_SENTRY_DSN`, `VITE_SENTRY_ENVIRONMENT`, `VITE_SENTRY_RELEASE`, `VITE_SENTRY_TRACES_SAMPLE_RATE`.
- Frontend sourcemap upload at build time: `BUILD_BUGSINK_URL`, `BUILD_BUGSINK_AUTH_TOKEN`, `BUILD_BUGSINK_PROJECT_SLUG`.

Only `VITE_` variables are compiled into browser code. Never prefix an auth token with `VITE_`. Set `SENTRY_ENABLE_SAMPLE_ROUTES=1` only temporarily when testing the backend error route.

## Development

Install dependencies and run backend tests:

```shell
uv sync --extra test
uv run pytest
```

Run frontend tests and the strict production build:

```shell
cd frontend
corepack yarn@4.9.2 install
corepack yarn@4.9.2 test
corepack yarn@4.9.2 build
```

Alembic revisions live in `alembic/`. The application automatically upgrades the local index on startup; use `uv run ai-usage db-upgrade` to do it explicitly.

## Troubleshooting

- **Discovery finds nothing:** verify the profile directory exists, or use `ai-usage provider add SERVICE PROVIDER --profile-dir ...` for manual configuration.
- **Claude status data is stale:** run `ai-usage claude-relay-install ACCOUNT_ID` to repair the relay, then use Claude once so its status line emits a fresh payload.
- **All providers fail:** run `ai-usage fetch` in the foreground; each account prints its own error.
- **Dashboard says “not built”:** run the frontend build before installing or serving from a source checkout.
- **Detached process exits:** inspect `~/.ai-usage/local/logs/detached.log`, or run the same command without `--detach`.
