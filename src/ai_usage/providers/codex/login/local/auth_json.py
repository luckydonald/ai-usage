"""Discovery of a local Codex profile by reusing its `auth.json`."""

from pathlib import Path

from ai_usage.providers.base import DiscoveredAccount, LoginMethod


class AuthJsonLogin(LoginMethod):
    key = "local-auth-json"
    display_name = "Reuse local auth.json"
    credential_kind = "app_token"

    async def discover(self) -> list[DiscoveredAccount]:
        auth_file = Path.home() / ".codex" / "auth.json"
        if auth_file.exists():
            return [DiscoveredAccount(name="Codex", options={"profile_dir": str(auth_file.parent)})]
        # end if
        return []
    # end def
# end class
