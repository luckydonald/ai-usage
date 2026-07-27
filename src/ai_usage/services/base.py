"""Shared service-management types and command helpers."""

from dataclasses import dataclass
from typing import Literal


ServiceMode = Literal["crawler", "webserver", "both"]


def service_arguments(mode: ServiceMode, host: str, port: int) -> list[str]:
    if mode == "crawler":
        return ["crawl"]
    # end if
    if mode == "webserver":
        return ["serve", "--host", host, "--port", str(port)]
    # end if
    return ["up", "--host", host, "--port", str(port)]
# end def


@dataclass(frozen=True, slots=True)
class ServiceStatus:
    installed: bool
    enabled: bool | None
    active: bool | None
    mode: ServiceMode | None
    detail: str
# end class
