"""Windows Task Scheduler integration."""

import subprocess
from pathlib import Path
from typing import Sequence

from ai_usage.services.base import ServiceMode, ServiceStatus
from ai_usage.services.linux import SERVICE_MARKER

TASK_NAME = "AI Usage"


def marker_path(local: Path) -> Path:
    return local / "ai-usage-task.txt"
# end def


def install(executable: str, arguments: Sequence[str], local: Path) -> Path:
    marker = marker_path(local)
    subprocess.run(["schtasks", "/Create", "/F", "/SC", "ONLOGON", "/TN", TASK_NAME, "/TR", " ".join([executable, *arguments])], check=True)
    marker.write_text(f"{SERVICE_MARKER}\n{' '.join(arguments)}\n", encoding="utf-8")
    return marker
# end def


def status(local: Path) -> ServiceStatus:
    marker = marker_path(local)
    if not marker.exists() or SERVICE_MARKER not in marker.read_text(encoding="utf-8"):
        return ServiceStatus(False, None, None, None, "not installed")
    # end if
    result = subprocess.run(["schtasks", "/Query", "/TN", TASK_NAME, "/FO", "LIST", "/V"], capture_output=True, text=True)
    arguments = marker.read_text(encoding="utf-8").splitlines()[-1].split()
    mode: ServiceMode = "both" if "up" in arguments else "webserver" if "serve" in arguments else "crawler"
    return ServiceStatus(True, True, result.returncode == 0 and "Running" in result.stdout, mode, str(marker))
# end def


def uninstall(local: Path) -> None:
    marker = marker_path(local)
    if marker.exists() and SERVICE_MARKER in marker.read_text(encoding="utf-8"):
        subprocess.run(["schtasks", "/Delete", "/F", "/TN", TASK_NAME], check=False)
        marker.unlink()
    # end if
# end def
