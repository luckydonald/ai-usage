/plan you shall write a ai token usage crawler.
The supported services shall for now be:
- codex
- claude
- copilot
However it shall be modular to later add new packages.
Additionally, there shall be the options to have multiple provider options per service (in the end auth token for api usage or cli output parsing), e.g.:
1. Use the internal token info API:
    - Services:
        - codex: search for api endpoint in https://chatgpt.com/codex/settings/usage
        - claude: api endpoint in https://claude.ai/new#settings/usage
        - copilot:
            - the ide plugins (i.e. `code`) seem to have an API endpoint for it.
            - it shows on the website https://github.com/settings/copilot/features.
    - with session auth via:
        1. the local filesystem based lookup
            - codex: ~/.codex/auth.json
            - claude: ??? + keychain on macOS
            - copilot: ???
        2. cli login:
            - codex: run auth flow for IDE integrations to get the token
            - …
        3. session cookies (interactive):
           - opens some webview etc. with the login URL, waits for logged in page, then grabs the required stuff from there.
        4. session cookies:
            - extract session cookies from common browsers
                - chrome
                - safari
                - firefox
- cli output:
    - codex: `codex '/status'` (call twice to have it re-fetch stale info)
        - Line `│  Weekly limit:         [███████████████████░] 94% left (resets 12:36 on 24 Jul) │`
    - claude: `claude '/usage'`:
        - ```text
            Current session
                                                               0% used
            Resets 7:50pm (Europe/Berlin)

            Current week (all models)
            ████                                               8% used
            Resets Jul 21, 10pm (Europe/Berlin)

            Current week (Fable)
                                                               0% used
          ```
    - copilot: not yet implemented in CLI, see https://github.com/github/copilot-cli/issues/3932
Generally:
- Universal provider interface, class interface based.
- Provides list of `Metric(name: str, usage: Usage(percentage: float) | MinMaxUsage(Usage)(current: int, max: int), resets: datetime | None)`
  - i.e. `"7-days"`, `"5-hours"`
- automatically loads from the providers, discovering existing files to import.
- Allows you to add services with `ai-usage add <service> <provider>`,
  - i.e. `ai-usage add claude login`
  - followed by TUI which asks for config values to be defined in the module
    - those must all be able to be set via `--foo=bar` as well to skip the interactive part completely.
  - the settings are stored in `~/.ai-usage/<service>/<some unique thing>.yml`
    - you can set colors per metric (i.e. `7-days`: some redish orange, `5-hours`: claude orange)
  - you are able to add multiple accounts with the same provider.
- `ai-usage fetch` is a one of command to now query all providers configured, and write the statistics to `~/.ai-usage/…`
- `ai-usage crawl` starts a loop to refresh those values every 10 minutes (user config). If a service just did a jump in it's usage (= it was used), decrease the fetch interval (default: `1 min`)
  - configurable as global, with per-service, per-service-provider and per-service-provider-configured-service (the `<some unique thing>`).
  - `-d` or `--detach` does detach it.
- `ai-usage serve` (`-p/--port`, `--host`) does change the ports and bound interface, default is `4458`, and localhost.
- `ai-usage run-all`: `crawl` + `serve` incl. TUI/flags
- `ai-usage install` does install `ai-usage` as a system startup thingo.
  - Asks same flags (flag or TUI) as `crawl`.
  - Also asks (flag or TUI) if it should enable the webserver for showing the stats.
    - Allows to configure the same flags as `serve` has, if chosen.
  - `-d` or `--detach` does detach it.
- `ai-usage uninstall` (or `deinstall`) undos the startup stuff.
- `ai-usage` alias for `run-all`

## The graphs

For each service I want to display the usage, and how it's consumed over time.
For that you can choose which configured services you want to display in the graph,
    - which metrics in general
    - filter by exact configured service
        - which metric of that service
    - service provider
    - service

It is basically a graph from `0%` - `100%` from bottom to top.
From left to right is time, choosable, default: last 24h if there's events otherwise scale up, 7 days, same day last month, year, all time
Using the percentage, it will build the graphs like the following:

Once a 0% is started to increase or otherwise a session is found as active (i.e. refresh time exist):
   1. Draw a limit box from start to refresh time
      - can also be a filled line/bar diagram part, whatever is easier, closing it at the bottom axis is not important.
      - 50% transparent fill
      - Border is 100% visible
      - the height as max value of datapoints within that
   2. Draw the datapoints as staircase like line diagram into the graph as well.
   3. If it is the current running interval: (i.e. restart time is in the future),
      1. display include that in the graph as well (increasing the time into the future)
      2. Estimate the end of usage (average of session) by adding a dotted line continuing the stair line as aproximation - i.e. a diagonal line instead of stairs.
      3. Draw a dotted 100% reset box, too.
   4. Once the session hits 100% color the remaining parts in that window in a user defined color (default: gray)
So you basically have the fine stairs of progress over time, and a max-usage per reset-window coarse stair over it to see generally how good you're using your limits.

## System
#### Backend:
- python 3.14+
- `asyncio`
- `pydantic`
- `fastapi` for the `serve` part
- `fastscheduler` for the `crawl` part
- Sentry
#### Frontend:
- Vue 3
- TS
- `<script setup lang="ts">`
- SCSS
- Support dark mode.
- Sentry

## Notes:
- The data files must be able to sync (=merge) via git.
- additional incompatible and unmergable indexing is okay though as long as it's not part of the git index — I.e. a folder with `.gitignore`, which will be rebuild after syncs.

