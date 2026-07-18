- Claude web returns 403, so we need to start with some kind of login.
   - list available options.
- Codex wants an endpoint still, but we should have figured out the endpoint by now. Probably needs login, too.
   - list available options for login
- the automatic git commit shall be a shared setting
- there is currently no proper setting for enabling/disabling the autocommit.
- separate the `ingest-claude`, `claude-relay-…` commands as a last internal tooling section in the `--help`.
- group the commands by what they do
- after a window ends, the graph display shall go to `0 %` automatically, even if the window end is not part of the current selected range.
- add custom range, showing two date pickers, both dates included.
- Remove everything except the graphs and build the website from scratch.
- Have our website use the following colors:
  - Usage | code | text color | description
    ------ | ------- | ------- | ----------
    primary | `#6C0DE9` | white | electric indigo (dark, for white text)
    second. | `#00C0DE` | black | sky surge (bright blue, a bit darkened)
    misc.   | `#FFC0DE` | black | blush pop (soft pink; also works well with primary)
    success | `#69F69F` | black | bright green
    error   | `#FF6969` | white | vibrant coral
  - `#6C0DE9` works with every other color
  - `#69F69F` and `#FFC0DE` are very bright and don't work together, but every other color can go on top.
- Have a function which generates the color pallets for in the frontend.
  - The idea is that all scarpers of one brand are the same base color, but still distingushable
    - codex graphs are based on `#99bd3c` (the full scale would be `#ee5091`, `#199fd7`, `#99bd3c`, `#fc7942`, `#8a50d8`, but we only use one for now)
    - claude graphs are based on `#DE7356`
    - preplexity (we don't have) would be `#21808D`
    - gemini (we don't have) would be `#9177C7` (of `#4796E3`, `#9177C7`, `#CA6673`)
    - cursor ai:
      - (we don't have)
      - Who would like to be called just "cursor", but the name us so badly chosen, it's literally the pointing device on your computer.
      - Therefore, always use "cursor ai" or "cursor code". This name would not be trademarkable in the EU.
      - `#72716D` (of `#43413C`, `#55544F`, `#72716D`, `#D6D5D2`, `#FFFFFF`)
- have completion file contain a hash of the input, so that we can detect changes, and update it when it's stale.
  - For simplicity, the update check shall be automatically on pretty much every command.
  - If no shell completion is installed (file missing) do nothing.
  - If it's out of sync:
    - No interactive session: Log a warning.
    - Interactive session: Ask to update it
      - yes (this time)
      - yes, always
      - no (this time)
      - no, not this new version
      - no, never
    - have a file with a dict with the hashes to version numbers, `dict[str, int]` so it's less confusing to users.
      - add a unittest confirming the current hash is in that dict.
