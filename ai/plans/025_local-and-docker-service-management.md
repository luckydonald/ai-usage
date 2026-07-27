# Local and Docker service management

## Summary

Keep `ai-usage up`, `start`, `crawl`, and `serve` unchanged. Add local and Docker service targets beneath `ai-usage service`.

## Implementation Changes

- Add `service local status|install|uninstall|deinstall` and `service docker status|install|uninstall|deinstall`.
- When `ai-usage service` has no target, prompt for `local` or `docker` only in an interactive terminal; otherwise fail with a usage error and render complete service help.
- Customize `ai-usage service --help` to list both targets, every nested action, and action parameters/flags.
- Split service management into shared dispatch plus dedicated Linux, macOS, Windows, and Docker modules.
  - Local install prompts for crawler, webserver, or both (default), with `--mode` for scripting; it manages the platform’s user-level startup facility.
  - Docker install selects the same mode and starts the matching Compose services; status reports Compose state; uninstall/deinstall removes containers but preserves data.
- Add a multi-stage, non-root Docker image.
- Add `docker-compose.yml` with root `name: ai-usage`, a persistent named data volume, separate crawler/webserver services, loopback-only port publication, and webserver health check.
- Add `docker-compose.coolify.yml` with a combined crawler/webserver service and an explicitly declared persistent data volume mounted as `/data`; it has no direct host port mapping and relies on Coolify’s configured domain/proxy.
- Update README for all service commands, direct Compose use, Coolify deployment, persistent data, initialization, and dashboard access security.

## Test and CI Plan

- Unit-test Linux, macOS, and Windows artifact generation, install/deinstall ownership protection, status parsing, and lifecycle command construction.
- CLI-test flattened service help, interactive target/mode defaults, noninteractive no-target failure/help, aliases, and unchanged top-level operate commands.
- Add a GitHub Actions workflow triggered on pushes and pull requests, with an Ubuntu/macOS/Windows matrix. Each runner installs Python/test dependencies and executes the install, deinstall, and status test suite against its platform-specific service module with external service commands mocked.
- Build/run the Docker stack on Linux; verify health, each Docker mode, data persistence, and both Compose-file configurations.

## Commit Handling

- On implementation, activate `$commit-with-lplp-style`: commit completed tasks, inspect the latest two commits, stage only task-owned files, and write messages through `ai/git/pending-commit.md`.
- Keep substantive plan revisions separate; fold eligible prompt/decision auto-commits into their associated implementation commit.

## Assumptions

- The image is built locally from this repository and is not published to a registry.
- Local Docker is loopback-only; Coolify uses its configured domain/proxy.
