"""Docker Compose lifecycle integration."""

import subprocess
from pathlib import Path

from ai_usage.services.base import ServiceMode, ServiceStatus


def compose_path() -> Path:
    candidate = Path.cwd() / "docker-compose.yml"
    if candidate.exists():
        return candidate
    # end if
    raise RuntimeError("docker service commands must run from a checkout containing docker-compose.yml")
# end def


def command(*arguments: str) -> list[str]:
    return ["docker", "compose", "-f", str(compose_path()), *arguments]
# end def


def install(mode: ServiceMode) -> None:
    selected = ["crawler"] if mode == "crawler" else ["webserver"] if mode == "webserver" else ["crawler", "webserver"]
    unselected = [service for service in ("crawler", "webserver") if service not in selected]
    if unselected:
        subprocess.run(command("stop", *unselected), check=False)
    # end if
    subprocess.run(command("up", "--detach", *selected), check=True)
# end def


def status() -> ServiceStatus:
    result = subprocess.run(command("ps", "--format", "json"), capture_output=True, text=True)
    if result.returncode != 0:
        return ServiceStatus(False, None, None, None, "compose stack is not installed")
    # end if
    active = "running" in result.stdout.lower()
    mode: ServiceMode | None = "both" if "crawler" in result.stdout and "webserver" in result.stdout else "crawler" if "crawler" in result.stdout else "webserver" if "webserver" in result.stdout else None
    return ServiceStatus(mode is not None, True if mode else None, active if mode else None, mode, result.stdout.strip() or "not installed")
# end def


def uninstall() -> None:
    subprocess.run(command("down"), check=True)
# end def
