"""Structured icon references, backed by the `fontawesome-free-pack` package."""

from importlib.metadata import version
from typing import Literal, NamedTuple

from fontawesome_free_pack import get_icon

IconSet = Literal["brands", "solid", "regular"]
ICON_SETS: frozenset[str] = frozenset({"brands", "solid", "regular"})

FONTAWESOME_FREE_PACK_VERSION = version("fontawesome-free-pack")


class IconRef(NamedTuple):
    name: str
    set: IconSet = "brands"
    pack: str = "fontawesome-free-pack"
    version: str = "latest"
# end class


def resolve_icon_svg(icon_set: str, name: str) -> str | None:
    """Return the SVG markup for a Font Awesome Free icon, or None if unknown."""
    if icon_set not in ICON_SETS:
        return None
    # end if
    icon = get_icon(f"{icon_set}/{name}")
    if icon is None:
        return None
    # end if
    return icon.svg
# end def
