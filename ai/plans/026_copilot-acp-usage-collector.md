# Copilot ACP `/usage` collector

## Summary

Add `copilot/cli-usage` as an additive provider. It will query Copilot through ACP, record only the account-level `Plan` allowance as an `AIC` min/max metric, and identify the active GitHub user through `/user show`. The existing token-backed `copilot/statusline` quota collector remains unchanged.

## Implementation changes

- Add a small async ACP-over-stdio client under the Copilot CLI usage package. It will initialize ACP, open a session with no MCP servers, send `/usage` and `/user show`, collect ordered text chunks, reject unexpected permission requests, enforce bounded request/process timeouts, and always terminate the child process.
- Start Copilot with only ACP-relevant, non-persistent restrictions: `--acp --stdio --reasoning-effort=none --available-tools= --disable-builtin-mcps --disallow-temp-dir --no-ask-user --no-auto-update --no-bash-env --no-custom-instructions --no-experimental --no-remote --no-remote-export`. Do not use `--interactive`, output/UI flags, or `--max-ai-credits`.
- Parse the `Plan` block such as `88% used` and `4,425/5,000 AIC` into one `plan` metric using `MinMaxUsage(current=4425, maximum=5000, unit="AIC")`; ignore ephemeral session token/credit counters. Missing or malformed Plan output is a clear provider error.
- Parse the active GitHub login returned by `/user show`, attach it as `AccountIdentity`, and use it for the provider’s canonical account identity.
- Register `CopilotCliUsageProvider` with key `cli-usage`, a configurable Copilot executable defaulting to `copilot`, and no stored credential or local-token reuse. Document `ai-usage provider add copilot cli-usage --no-input` and add it to the collection-method table.

## Test plan

- Unit-test usage parsing for comma-separated AIC amounts, flexible whitespace, invalid/missing Plan blocks, and the chosen GitHub-user output.
- Test ACP request sequencing, streamed chunk assembly, ignored notifications, rejected permission requests, timeouts, process failures, and cleanup with a fake line-oriented ACP process.
- Test provider registration and fetch results: `copilot/cli-usage`, one `plan` metric, and persisted login identity.
- Run the focused provider/CLI tests; optionally smoke-test against an authenticated local Copilot CLI without recording raw command output.

## Assumptions

- The installed Copilot CLI supports ACP and `--reasoning-effort=none` (confirmed for local CLI 1.0.75).
- `/usage` continues to expose account Plan allowance independently of the fresh ACP session; session-only statistics remain intentionally out of scope.
