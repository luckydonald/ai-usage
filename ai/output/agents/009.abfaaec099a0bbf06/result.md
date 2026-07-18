Enough info for report.

Directive: research credential/login flow options for claude/web and codex/web providers (403/missing endpoint, no login mechanism yet).

Findings:

1. Credential shape: `Provider.fetch(account, credential)` — `credential: dict[str,Any]|None` (base.py:29,53). claude.py:200-201 and codex.py:178-179 pull `credential.get("cookies", {})` and `.get("headers", {})`, feed into `httpx.AsyncClient(cookies=cookies, headers=headers, base_url=...)`. Codex additionally has separate app-server auth via `credential["auth_json"]` written to a file (codex.py:333-336), unrelated to web provider.

2. No dedicated `credential.py`. Credentials flow: CLI `provider add` (cli.py:358-465) accepts `--secret-json` / `--secret-file` (JSON blob), parsed via `parsed_credential()` (cli.py:268-269→124), then `runtime.database.put_credential(provider_key, account_name, credential)` (cli.py:185) which encrypts via `CredentialCipher` (crypto.py, AES-GCM, key from `AI_USAGE_CREDENTIAL_KEY` env or `paths.local/credential.key` file, settings.py:17,35,46-48) and stores in `CredentialRecord` table (orm.py, referenced by `account.credential_id`). So today's only path to supply cookies: user manually crafts `{"cookies": {...}}` JSON and passes via `--secret-json`/`--secret-file` at `provider add` time. No browser-cookie auto-import, no OAuth/device flow, no interactive login command anywhere (`grep cookie` hits only the 3 provider files consuming the dict — nothing produces it).

3. CLI command groups: top-level `app`: `fetch`, `crawl`, `install`, `completion`, `uninstall`, `db-upgrade`, `history-cleanup`, `up`, `serve`, `ingest-claude`, `claude-relay-install`, `claude-relay-remove`. `provider_app` (sub): `add`, `discover`, `list`, `status`, `remove`, `rename`, `merge`. `hosts_app` (sub): `add`, `remove`.

Options for a login flow (ranked):
- **A. claude-in-chrome-driven interactive login** (best fit, since MCP already used this session): a new `provider add claude/web` / `codex/web` interactive step that drives the existing MCP tool to open the site, wait for user to confirm login, then reads `document.cookie` / uses `navigate`+`read_network_requests` to capture the session cookie jar, feeds it straight into `credential = {"cookies": {...}}` and calls existing `put_credential`. Zero new deps, reuses today's storage path end-to-end. Downside: only works when invoked from a session with claude-in-chrome connected (not headless/cron).
- **B. Manual cookie paste command**: extend `provider add` (or dedicated `provider login`) to prompt "paste your `document.cookie` string" and parse `key=val; key2=val2` into the dict. Zero new deps, works headless, but manual/annoying and cookies expire.
- **C. browser_cookie3 auto-import**: new dependency, reads cookies directly from the user's actual installed browser's cookie store on disk. Works headless-ish (same machine only), no MCP dependency, but needs new dep + OS keychain unlock handling (Chrome's own cookie encryption) — heavier lift.
- **D. Playwright-driven interactive login**: spin a real headed browser, let user log in manually, capture cookies via `context.cookies()`. New dependency (playwright + browser binaries), heavier install, but works independent of Claude Code being open in a session — most portable long-term, most implementation cost now.

Given this session already has claude-in-chrome loaded and working, **A** is the cheapest path to unblock claude/web + codex/web today; B is a good zero-dep fallback for headless crawl re-auth.