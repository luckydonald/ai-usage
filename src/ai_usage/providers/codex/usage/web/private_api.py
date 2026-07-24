"""Codex private web API usage method (chatgpt.com backend-api)."""

import logging
import re
from datetime import UTC, datetime
from typing import Any

from curl_cffi.requests import AsyncSession
from pydantic import BaseModel, ValidationError

from ai_usage.models import (
    AccountConfig,
    AccountIdentity,
    Metric,
    ProviderFetchResult,
    SubscriptionStatus,
    Usage,
)
from ai_usage.providers.base import CredentialKind, ProviderError, UsageMethod

LOGGER = logging.getLogger(__name__)


def window_key(minutes: int) -> str:
    known = {300: "five-hours", 10080: "seven-days"}
    return known.get(minutes, f"window-{minutes}-minutes")
# end def


def window_name(minutes: int) -> str:
    if minutes % 10080 == 0:
        return f"{minutes // 10080} week"
    elif minutes % 1440 == 0:
        return f"{minutes // 1440} day"
    elif minutes % 60 == 0:
        return f"{minutes // 60} hour"
    # end if
    return f"{minutes} minute"
# end def


MODEL_PATTERN = re.compile(r"model:\s*(?P<model>\S.*?)\s{2,}/model to change", re.IGNORECASE)


def codex_model(output: str) -> str | None:
    match = MODEL_PATTERN.search(output)
    return match.group("model").strip() if match else None
# end def


NOTE_PATTERN = re.compile(
    r"You have \d+ usage limit resets? available\. Run /usage to use one\.", re.IGNORECASE
)


def extract_codex_notes(output: str) -> list[str]:
    return [match.group(0).strip() for match in NOTE_PATTERN.finditer(output)]
# end def


def parse_rate_limits(payload: dict[str, Any], observed_at: datetime) -> list[Metric]:
    rate_limits = payload.get("rateLimits") or payload.get("rate_limits") or {}
    metrics: list[Metric] = []
    for slot in ("primary", "secondary"):
        window = rate_limits.get(slot)
        if not window:
            continue
        # end if
        minutes = int(window["windowDurationMins"])
        metrics.append(
            Metric(
                key=window_key(minutes),
                name=window_name(minutes),
                usage=Usage(percentage=float(window["usedPercent"])),
                observed_at=observed_at,
                reset_at=datetime.fromtimestamp(int(window["resetsAt"]), UTC),
                window_seconds=minutes * 60,
                metadata={"slot": slot},
            )
        )
    # end for
    return metrics
# end def


def codex_app_server_email(payload: dict[str, Any]) -> str | None:
    account = payload.get("account")
    values = (
        payload.get("email"),
        account.get("email") if isinstance(account, dict) else None,
        account.get("emailAddress") if isinstance(account, dict) else None,
    )
    return next((value for value in values if isinstance(value, str)), None)
# end def


class CodexRateWindowPayload(BaseModel):
    used_percent: float | None = None
    limit_window_seconds: int | None = None
    reset_at: int | None = None
# end class


class CodexRateLimitPayload(BaseModel):
    primary_window: CodexRateWindowPayload | None = None
    secondary_window: CodexRateWindowPayload | None = None
# end class


class CodexWhamUsagePayload(BaseModel):
    account_id: str | None = None
    email: str | None = None
    plan_type: str | None = None
    rate_limit: CodexRateLimitPayload | None = None
# end class


def parse_codex_web_usage(payload: dict[str, Any], observed_at: datetime) -> list[Metric]:
    try:
        parsed = CodexWhamUsagePayload.model_validate(payload)
        slots: dict[str, CodexRateWindowPayload | dict[str, Any] | None] = (
            {
                "primary": parsed.rate_limit.primary_window,
                "secondary": parsed.rate_limit.secondary_window,
            }
            if parsed.rate_limit is not None
            else {}
        )
    except ValidationError as exception:
        LOGGER.warning(
            "Codex usage payload did not match the expected schema, falling back to raw "
            "field access: %s",
            exception,
        )
        raw_rate_limit = payload.get("rate_limit")
        raw_rate_limit = raw_rate_limit if isinstance(raw_rate_limit, dict) else {}
        slots = {
            "primary": raw_rate_limit.get("primary_window"),
            "secondary": raw_rate_limit.get("secondary_window"),
        }
    # end try
    metrics: list[Metric] = []
    for slot, window in slots.items():
        if window is None:
            continue
        # end if
        try:
            if isinstance(window, CodexRateWindowPayload):
                used_percent, limit_window_seconds, reset_at = (
                    window.used_percent,
                    window.limit_window_seconds,
                    window.reset_at,
                )
            elif isinstance(window, dict):
                used_percent = window.get("used_percent")
                limit_window_seconds = window.get("limit_window_seconds")
                reset_at = window.get("reset_at")
            else:
                continue
            # end if
            if not isinstance(used_percent, int | float) or not limit_window_seconds:
                continue
            # end if
            minutes = int(limit_window_seconds) // 60
            metrics.append(
                Metric(
                    key=window_key(minutes),
                    name=window_name(minutes),
                    usage=Usage(percentage=float(used_percent)),
                    observed_at=observed_at,
                    reset_at=datetime.fromtimestamp(int(reset_at), UTC) if reset_at else None,
                    window_seconds=minutes * 60,
                    metadata={"slot": slot},
                )
            )
        except (ValueError, TypeError) as exception:
            LOGGER.warning("could not parse Codex %s rate limit window: %s", slot, exception)
        # end try
    # end for
    return metrics
# end def


class PrivateApiUsage(UsageMethod):
    """Fetches Codex usage from chatgpt.com's private backend-api via curl_cffi."""

    required_credential_kind: CredentialKind = "cookie_jar"

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        cookies = (credential or {}).get("cookies", {})
        headers = (credential or {}).get("headers", {})
        observed = datetime.now(UTC)
        # chatgpt.com sits behind Cloudflare, which ties its `cf_clearance` cookie to the TLS/HTTP
        # client fingerprint that solved the challenge -- a plain httpx client gets 403'd even with
        # otherwise-valid cookies. `impersonate="chrome"` makes curl_cffi present a real Chrome
        # TLS fingerprint instead, which Cloudflare accepts alongside the captured cookies.
        async with AsyncSession(
            timeout=20, cookies=cookies, headers=headers, base_url="https://chatgpt.com",
            impersonate="chrome",
        ) as client:
            session_response = await client.get("/api/auth/session")
            if session_response.status_code != 200:
                raise ProviderError(
                    f"Codex session endpoint returned HTTP {session_response.status_code}"
                )
            # end if
            session_payload = session_response.json()
            access_token = session_payload.get("accessToken")
            if not access_token:
                raise ProviderError("Codex session response did not contain an access token")
            # end if
            usage_response = await client.get(
                "/backend-api/wham/usage",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if usage_response.status_code != 200:
                raise ProviderError(
                    f"Codex usage endpoint returned HTTP {usage_response.status_code}"
                )
            # end if
            usage_payload = usage_response.json()
        # end with
        metrics = parse_codex_web_usage(usage_payload, observed)
        if not metrics:
            raise ProviderError("Codex usage response did not contain any rate limit windows")
        # end if
        identity = AccountIdentity(email=usage_payload.get("email"))
        subscription = SubscriptionStatus(plan_type=usage_payload.get("plan_type"))
        return ProviderFetchResult(
            service="codex",
            provider="web",
            account_id=account.id,
            fetched_at=observed,
            metrics=metrics,
            identity=identity,
            subscription=subscription,
            raw_payload={
                "session_user": session_payload.get("user"),
                "session_account": session_payload.get("account"),
                "usage": usage_payload,
            },
        )
    # end def
# end class
