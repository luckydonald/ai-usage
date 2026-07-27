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
import re
import subprocess
from typing import Any

from ai_usage.providers.base import DiscoveredAccount, LoginMethod

GITHUB_TOKEN_ENV_VARS = ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")


def configured_login(config_text: str, config: dict[str, Any]) -> str | None:
    """Read the selected user from legacy JSON or the current JSONC config."""
    last_user = config.get("last_logged_in_user", config.get("lastLoggedInUser"))
    last_user = last_user if isinstance(last_user, dict) else {}
    if login := last_user.get("login"):
        return login if isinstance(login, str) else None
    # end if
    match = re.search(r'"lastLoggedInUser"\s*:\s*\{(?P<user>[^{}]*)\}', config_text)
    if not match:
        return None
    # end if
    login_match = re.search(r'"login"\s*:\s*"(?P<login>[^"]+)"', match.group("user"))
    return login_match.group("login") if login_match else None
# end def


def keyring_token() -> str | None:
    """Read the OAuth token that current Copilot CLI stores in Linux libsecret."""
    try:
        result = subprocess.run(
            ["secret-tool", "lookup", "service", "copilot-cli"],
            capture_output=True,
            check=False,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    # end try
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None
# end def


def copilot_cli_credentials(config_dir: Path) -> tuple[str | None, str | None]:
    """Reuse the Copilot CLI's own stored OAuth token, so no separate PAT is needed.

    Returns `(token, github_login)`; either element may be `None` when it can't be
    determined. Supports legacy plaintext `copilot_tokens` and the current CLI's
    libsecret keyring storage, after checking environment variables first.
    """
    for env_var in GITHUB_TOKEN_ENV_VARS:
        if token := os.environ.get(env_var):
            return token, None
        # end if
    # end for
    try:
        config_text = (config_dir / "config.json").read_text(encoding="utf-8")
    except OSError:
        return None, None
    # end try
    try:
        config = json.loads(config_text)
    except json.JSONDecodeError:
        config = {}
    # end try
    tokens = config.get("copilot_tokens")
    tokens = tokens if isinstance(tokens, dict) else {}
    last_user = config.get("last_logged_in_user", config.get("lastLoggedInUser"))
    last_user = last_user if isinstance(last_user, dict) else {}
    login = configured_login(config_text, config)
    host = last_user.get("host") if isinstance(last_user.get("host"), str) else None
    if login and host and (token := tokens.get(f"{host}:{login}")):
        return token, login
    # end if
    for token in tokens.values():
        if token:
            return token, login
        # end if
    # end for
    return keyring_token(), login
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

    async def authenticate(self, options: dict[str, Any]) -> dict[str, Any] | None:
        """Reuse the local session when manually adding the provider."""
        config_dir = Path(str(options.get("config_dir", Path.home() / ".copilot")))
        token, login = copilot_cli_credentials(config_dir)
        if not token:
            return None
        # end if
        return {"token": token, "login": login}
    # end def
# end class
