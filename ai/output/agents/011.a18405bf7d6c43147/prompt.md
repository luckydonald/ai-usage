Research-only, no edits. Scoping a plan for a shell-completion staleness-check feature in this repo (ai-usage, Python/Typer CLI).

Investigate and report back (under 300 words):
1. Does this repo currently generate/install shell completion files (Typer/Click has built-in `--install-completion`/`--show-completion`)? grep for "completion" across src/ and any docs/README.
2. If Typer's built-in completion is used, where does it write the completion script (bash/zsh/fish paths are shell-dependent, typically `~/.bash_completion.d/`, `~/.zfunc/`, etc.) — is there a repo-specific wrapper around this, or is it purely Typer's default `--install-completion` behavior with no custom code?
3. Is there any existing "version" or "hash of CLI structure" tracking anywhere (e.g. for detecting when the CLI's command tree changed)? Check for a VERSION file, `__version__`, pyproject.toml version, or similar.
4. Is there an existing "is this an interactive session" check anywhere in the codebase (e.g. `sys.stdin.isatty()`) used for other yes/no prompts? Report pattern used, if any, with file:line.

Report file:line refs. Don't design the feature, just report current relevant state (or confirm each piece is entirely absent).