# Group Provider Registration Commands

## Summary

Replace the flat registration commands with a singular `ai-usage provider` command group. Discovery drives interactive account registration, while configured-account management gains listing, status, soft removal, and optional history purging.

Remove the old top-level `add`, `discover`, and `providers` commands rather than retaining compatibility aliases.

## CLI Contract

| Command | Aliases | Behavior |
| --- | --- | --- |
| `provider discover [SERVICE] [PROVIDER]` | — | Run discovery across all matching adapters and enumerate importable local accounts. |
| `provider add [SERVICE] [PROVIDER]` | `new` | Add a discovered account or manually configure an adapter. |
| `provider list [SERVICE] [PROVIDER]` | `ls` | List matching configured accounts, including soft-removed accounts and their state. |
| `provider status [SERVICE] [PROVIDER] [ACCOUNT]` | `info` | Show configuration, credential availability, latest usage, last fetch result, and crawl state. |
| `provider remove [SERVICE] [PROVIDER] [ACCOUNT]` | `del`, `rm` | Soft-remove an account or permanently purge it with `--delete-history`. |

- `status` and `remove` also accept `--account=UUID`, which bypasses service/provider selection.
- `discover` and `list` enumerate all matches when filters are omitted.
- Interactive `add`, `status`, and `remove` use a Textual selection TUI for omitted or ambiguous targets.
- Non-TTY execution, or explicit `--no-input`, prints the available choices and exits successfully without mutation when required targeting is missing.
- Existing provider-specific flags, `--secret-json`, and `--secret-file` remain supported by `provider add`.

## Discovery and Account Lifecycle

- Run matching providers’ `discover()` methods concurrently, isolate individual discovery failures, and present successful candidates with service, provider, account name, and relevant non-secret details.
- The initial add screen lists discovered accounts only, followed by one `Manually configure other…` entry. Selecting it opens a second adapter-selection screen rather than flooding the primary list.
- Selecting a discovered account preloads its name, options, and credential. Explicit CLI options override discovered values; discovered credentials are encrypted through the existing credential store.
- Store a stable discovery fingerprint on configured accounts. If a discovered candidate matches a soft-removed account, restore the same UUID and history, clear `removed_at`, enable it, recreate credentials, and reinstall integrations.
- Extend account YAML with nullable `removed_at`. Soft removal sets `enabled: false`, clears `credential_id`, removes the encrypted credential row, crawl/fetch state, and Claude relay integration, but retains the full non-secret YAML configuration and JSONL history.
- Interactive removal asks whether history should also be deleted, defaulting to preservation. Non-interactive removal preserves history unless `--delete-history` is supplied.
- History-inclusive removal deletes the account’s JSONL tree, corresponding SQLite index rows, remaining runtime state, and tombstone YAML. Repeating soft removal is idempotent; a later `--delete-history` invocation finalizes deletion.
- `status` never performs a live fetch. It reports stored state and redacts all credential content.

## Tests and Documentation

- Add CLI tests for the command hierarchy, every alias, removal of old flat commands, optional filters, `--account` bypass, and non-interactive choice output.
- Add Textual pilot tests for discovered-account selection, the manual submenu, ambiguous account selection, cancellation, and removal’s history prompt.
- Test discovered-option precedence, encrypted discovered credentials, fingerprint-based tombstone restoration, and isolated discovery failures.
- Test list/status output for active, failed, empty-history, and soft-removed accounts.
- Test soft removal, repeated removal, credential/runtime cleanup, Claude relay restoration, preserved history, and permanent history/index/config purging.
- Update README examples, command tables, shell-completion expectations, and removal safety documentation.
- Run backend tests and CLI help smoke checks, then commit the completed feature using the active lplp commit style.

## Assumptions

- Human-readable tables are sufficient; no JSON output format is added.
- A fully specified service/provider with exactly one matching configured account may resolve automatically; ambiguous matches require selection or an account UUID.
- Invalid explicit identifiers remain errors, while omission in non-interactive mode is informational and exits without changing state.
- Disabled full configuration is retained because provider options are non-secret; actual secret material remains exclusively in encrypted SQLite storage and is deleted during soft removal.
