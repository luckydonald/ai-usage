"""Filesystem and environment settings."""

import os
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_config_path


@dataclass(frozen=True, slots=True)
class Paths:
    root: Path
    services: Path
    history: Path
    local: Path
    database: Path
    credential_key: Path
    logs: Path
    frontend: Path

    @classmethod
    def from_environment(cls) -> "Paths":
        configured_root = os.environ.get("AI_USAGE_HOME")
        root = Path(configured_root).expanduser() if configured_root else Path.home() / ".ai-usage"
        package_root = Path(__file__).resolve().parents[2]
        installed_frontend = Path(__file__).resolve().parent / "frontend"
        source_frontend = package_root / "frontend" / "dist"
        frontend = installed_frontend if installed_frontend.exists() else source_frontend
        return cls(
            root=root,
            services=root / "services",
            history=root / "history",
            local=root / "local",
            database=root / "local" / "state.sqlite3",
            credential_key=root / "local" / "credential.key",
            logs=root / "local" / "logs",
            frontend=frontend,
        )
    # end def

    def ensure(self) -> None:
        for directory in (self.root, self.services, self.history, self.local, self.logs):
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            directory.chmod(0o700)
        # end for
        legacy_credential_key = self.root / "credential.key"
        if legacy_credential_key.exists() and not self.credential_key.exists():
            legacy_credential_key.rename(self.credential_key)
        # end if
        gitignore = self.root / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("/local/\n", encoding="utf-8")
        # end if
    # end def
# end class


def default_paths() -> Paths:
    return Paths.from_environment()
# end def


def legacy_config_path() -> Path:
    """Return the platform-native location for future migration tooling."""
    return user_config_path("ai-usage")
# end def
