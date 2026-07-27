"""launchd user-service integration."""

import os
import plistlib
import subprocess
from pathlib import Path
from typing import Sequence

from ai_usage.services.base import ServiceMode, ServiceStatus
from ai_usage.services.linux import SERVICE_MARKER

LABEL = "com.ai-usage.service"


def target_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
# end def


def plist(executable: str, arguments: Sequence[str], logs: Path) -> bytes:
    return plistlib.dumps({"Label": LABEL, "ProgramArguments": [executable, *arguments], "RunAtLoad": True, "KeepAlive": True, "StandardOutPath": str(logs / "service.log"), "StandardErrorPath": str(logs / "service-error.log"), "AIUsageMarker": SERVICE_MARKER})
# end def


def install(executable: str, arguments: Sequence[str], logs: Path) -> Path:
    target = target_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(plist(executable, arguments, logs))
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(target)], check=False)
    subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(target)], check=True)
    return target
# end def


def status() -> ServiceStatus:
    target = target_path()
    if not target.exists() or SERVICE_MARKER not in target.read_text(encoding="utf-8", errors="ignore"):
        return ServiceStatus(False, None, None, None, "not installed")
    # end if
    active = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"], capture_output=True).returncode == 0
    payload = plistlib.loads(target.read_bytes())
    arguments = payload["ProgramArguments"]
    mode: ServiceMode = "both" if "up" in arguments else "webserver" if "serve" in arguments else "crawler"
    return ServiceStatus(True, True, active, mode, str(target))
# end def


def uninstall() -> None:
    target = target_path()
    if target.exists() and SERVICE_MARKER in target.read_text(encoding="utf-8", errors="ignore"):
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(target)], check=False)
        target.unlink()
    # end if
# end def
