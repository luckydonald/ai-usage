"""Human-readable collection progress reporting."""

from collections.abc import Callable

ProgressReporter = Callable[[str], None]


def quiet_reporter(message: str) -> None:
    del message
# end def


def percentage(value: float | None) -> str:
    if value is None:
        return "no previous value"
    # end if
    rendered = f"{value:.1f}".rstrip("0").rstrip(".")
    return f"{rendered}%"
# end def
