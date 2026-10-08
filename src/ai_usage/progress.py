"""Human-readable collection progress reporting."""

import logging
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


def account_reporter(report: ProgressReporter, service: str, provider: str) -> ProgressReporter:
    """Route a logger-backed reporter to the crawler's own child logger, e.g. `ai_usage.crawl.claude.web_ai`.

    Reporters that are not bound `Logger` methods (tests, quiet mode) are returned unchanged.
    """
    logger = getattr(report, "__self__", None)
    if not isinstance(logger, logging.Logger):
        return report
    # end if
    child = logging.getLogger(f"{logger.name}.{service.replace('.', '_')}.{provider.replace('.', '_')}")
    return getattr(child, report.__name__)
# end def
