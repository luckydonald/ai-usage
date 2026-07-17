"""Opt-in backend Sentry initialization and build metadata."""

import os
import subprocess
from pathlib import Path


def command_value(*arguments: str) -> str:
    try:
        return subprocess.check_output(arguments, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.SubprocessError):
        return ""
    # end try
# end def


def file_value(name: str) -> str:
    path = Path(__file__).resolve().parents[2] / name
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""
# end def


GIT_COMMIT = os.environ.get("SOURCE_COMMIT") or command_value("git", "rev-parse", "HEAD") or file_value(
    "git-commit.txt"
) or "unknown"
GIT_BRANCH = os.environ.get("GIT_BRANCH") or command_value(
    "git", "rev-parse", "--abbrev-ref", "HEAD"
) or file_value("git-branch.txt") or "unknown"
BUILD_TIME = os.environ.get("BUILD_TIME") or file_value("build-time.txt") or "unknown"


def sample_rate(value: str | None) -> float:
    if not value:
        return 0.0
    # end if
    parsed = float(value)
    if not 0 <= parsed <= 1:
        raise ValueError("SENTRY_TRACES_SAMPLE_RATE must be between 0 and 1")
    # end if
    return parsed
# end def


def init_sentry() -> None:
    dsn = os.environ.get("SENTRY_DSN", "")
    if not dsn:
        return
    # end if
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("SENTRY_ENVIRONMENT") or None,
        release=os.environ.get("SENTRY_RELEASE") or GIT_COMMIT,
        dist=BUILD_TIME,
        integrations=[FastApiIntegration(), StarletteIntegration()],
        send_default_pii=False,
        traces_sample_rate=sample_rate(os.environ.get("SENTRY_TRACES_SAMPLE_RATE")),
    )
    sentry_sdk.set_tag("git_commit", GIT_COMMIT)
    sentry_sdk.set_tag("git_branch", GIT_BRANCH)
    sentry_sdk.set_tag("build_time", BUILD_TIME)
# end def


def capture_exception(exception: BaseException) -> None:
    if not os.environ.get("SENTRY_DSN"):
        return
    # end if
    import sentry_sdk

    sentry_sdk.capture_exception(exception)
# end def

