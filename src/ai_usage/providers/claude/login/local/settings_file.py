"""Discovery of a local Claude CLI profile (no credential is needed or stored)."""

from pathlib import Path

from ai_usage.providers.base import DiscoveredAccount, LoginMethod


class SettingsFileLogin(LoginMethod):
    key = "settings_file"
    display_name = "Local Claude CLI settings"
    credential_kind = "none"

    async def discover(self) -> list[DiscoveredAccount]:
        settings = Path.home() / ".claude" / "settings.json"
        if settings.exists():
            return [DiscoveredAccount(name="Claude", options={"profile_dir": str(settings.parent)})]
        # end if
        return []
    # end def
# end class
