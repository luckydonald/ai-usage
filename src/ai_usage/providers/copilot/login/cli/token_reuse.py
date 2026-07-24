"""Copilot CLI local token reuse login method.

Combines what used to be two separate concerns in the old flat `copilot.py`:

- `CopilotStatusProvider.discover()` probing for `~/.copilot/config.json`.
- `copilot_cli_credentials()` being called *inline inside* `CopilotStatusProvider.fetch()`
  to resolve an actual bearer token (from env vars, or that same config file).

Both read the exact same on-disk/env-var source, so a separate `ConfigFileLogin` that
only re-probed the file's existence (without being able to produce a usable credential
itself) would be a near-duplicate. This single `LoginMethod` covers both: `discover()`
now does the full resolution (probe + token extraction) so the credential handed to
`QuotaApiUsage.fetch()` is already resolved, matching the plan's requirement that
usage-time login side effects move out of `fetch()`.
"""

import json
import os
from pathlib import Path

from ai_usage.providers.base import DiscoveredAccount, LoginMethod

GITHUB_TOKEN_ENV_VARS = ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")


def copilot_cli_credentials(config_dir: Path) -> tuple[str | None, str | None]:
    """Reuse the Copilot CLI's own stored OAuth token, so no separate PAT is needed.

    Returns `(token, github_login)`; either element may be `None` when it can't be
    determined. Mirrors how community Copilot CLI status-line scripts resolve a token:
    environment variables first, then `~/.copilot/config.json`'s `copilot_tokens` map.
    """
    for env_var in GITHUB_TOKEN_ENV_VARS:
        if token := os.environ.get(env_var):
            return token, None
        # end if
    # end for
    config_path = config_dir / "config.json"
    if not config_path.exists():
        return None, None
    # end if
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None, None
    # end try
    tokens = config.get("copilot_tokens")
    tokens = tokens if isinstance(tokens, dict) else {}
    last_user = config.get("last_logged_in_user")
    last_user = last_user if isinstance(last_user, dict) else {}
    login = last_user.get("login") if isinstance(last_user.get("login"), str) else None
    host = last_user.get("host") if isinstance(last_user.get("host"), str) else None
    if login and host and (token := tokens.get(f"{host}:{login}")):
        return token, login
    # end if
    for token in tokens.values():
        if token:
            return token, login
        # end if
    # end for
    return None, login
# end def


class TokenReuseLogin(LoginMethod):
    """Discovers/reuses a Copilot CLI (or env var) OAuth token as a bearer credential."""

    key = "cli-token-reuse"
    display_name = "Reuse Copilot CLI session"
    credential_kind = "bearer_token"

    async def discover(self) -> list[DiscoveredAccount]:
        config_dir = Path.home() / ".copilot"
        token, login = copilot_cli_credentials(config_dir)
        if not token:
            return []
        # end if
        return [
            DiscoveredAccount(
                name=login or "Copilot",
                options={"config_dir": str(config_dir)},
                credential={"token": token, "login": login},
            )
        ]
    # end def
# end class
