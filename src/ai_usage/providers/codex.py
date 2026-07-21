"""Codex app-server and terminal status providers."""

import asyncio
import json
import logging
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from curl_cffi.requests import AsyncSession
from pydantic import BaseModel, ValidationError

from ai_usage.icons import IconRef
from ai_usage.models import (
    AccountConfig,
    AccountIdentity,
    FetchStatus,
    Metric,
    ProviderFetchResult,
    SubscriptionStatus,
    Usage,
)
from ai_usage.providers.base import ConfigurationField, DiscoveredAccount, Provider, ProviderError
from ai_usage.webview_login import capture_cookies_via_webview

LOGGER = logging.getLogger(__name__)

STATUS_PATTERN = re.compile(
    r"(?P<name>Weekly|\d+\s*hour)\s+limit:\s+.*?(?P<remaining>\d+(?:\.\d+)?)%\s+left\s+"
    r"\(resets\s+(?P<reset>[^)]+)\)",
    re.IGNORECASE,
)

STALE_WARNING_PATTERN = re.compile(r"limits may be stale", re.IGNORECASE)
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


class CodexWebUsageProvider(Provider):
    service = "codex"
    key = "web"
    display_name = "Codex private web API"
    icon = IconRef(set="solid", name="globe")
    login_url = "https://chatgpt.com/"
    login_button_selector = '[data-testid="login-button"]'
    # chatgpt.com's CSP forbids 'unsafe-eval', which is exactly how pywebview injects JS — the
    # auto-click attempt (below) always fails there, so tell the user up front rather than let
    # them wonder why nothing happens.
    login_hint = "Click \"Log in\" once the page loads."

    async def authenticate(self, options: dict[str, Any]) -> dict[str, Any] | None:
        del options
        # pywebview must run on the main thread (it raises WebViewException otherwise), so this
        # is a deliberate synchronous, blocking call rather than `asyncio.to_thread(...)`.
        cookies = capture_cookies_via_webview(
            self.login_url, self.display_name, click_selector=self.login_button_selector
        )
        return {"cookies": cookies} if cookies else None
    # end def

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        cookies = (credential or {}).get("cookies", {})
        headers = (credential or {}).get("headers", {})
        observed = datetime.now(UTC)
        # chatgpt.com sits behind Cloudflare, which ties its `cf_clearance` cookie to the TLS/HTTP
        # client fingerprint that solved the challenge — a plain httpx client gets 403'd even with
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
            service=self.service,
            provider=self.key,
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


class AppServerClient:
    def __init__(self, command: str, environment: dict[str, str]):
        self.command = command
        self.environment = environment
        self.process: asyncio.subprocess.Process | None = None
        self.request_id = 0
    # end def

    async def __aenter__(self) -> "AppServerClient":
        self.process = await asyncio.create_subprocess_exec(
            self.command,
            "app-server",
            "--stdio",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self.environment,
        )
        await self.request(
            "initialize",
            {"clientInfo": {"name": "ai-usage", "title": "AI Usage", "version": "0.1.0"}},
        )
        await self.notify("initialized", {})
        return self
    # end def

    async def __aexit__(self, exception_type: Any, exception: Any, traceback: Any) -> None:
        del exception_type, exception, traceback
        if self.process is not None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=3)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
            # end try
        # end if
    # end def

    async def send(self, payload: dict[str, Any]) -> None:
        if self.process is None or self.process.stdin is None:
            raise ProviderError("Codex app-server is not running")
        # end if
        self.process.stdin.write(json.dumps(payload, separators=(",", ":")).encode() + b"\n")
        await self.process.stdin.drain()
    # end def

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        await self.send({"method": method, "params": params})
    # end def

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.process is None or self.process.stdout is None:
            raise ProviderError("Codex app-server is not running")
        # end if
        self.request_id += 1
        request_id = self.request_id
        payload: dict[str, Any] = {"method": method, "id": request_id}
        if params is not None:
            payload["params"] = params
        # end if
        await self.send(payload)
        while line := await asyncio.wait_for(self.process.stdout.readline(), timeout=30):
            message = json.loads(line)
            if message.get("id") != request_id:
                continue
            # end if
            if "error" in message:
                raise ProviderError(f"Codex {method} failed: {message['error']}")
            # end if
            result: dict[str, Any] = message.get("result") or {}
            return result
        # end while
        raise ProviderError(f"Codex app-server closed while waiting for {method}")
    # end def
# end class


class CodexAppServerProvider(Provider):
    service = "codex"
    key = "app-server"
    display_name = "Codex app-server"
    icon = IconRef(set="solid", name="server")
    configuration_fields = (
        ConfigurationField(key="command", label="Codex executable", default="codex"),
        ConfigurationField(key="profile_dir", label="Codex profile", kind="path"),
    )

    async def discover(self) -> list[DiscoveredAccount]:
        auth_file = Path.home() / ".codex" / "auth.json"
        if auth_file.exists():
            return [DiscoveredAccount(name="Codex", options={"profile_dir": str(auth_file.parent)})]
        # end if
        return []
    # end def

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        environment = dict(os.environ)
        profile_dir = account.options.get("profile_dir")
        temporary: tempfile.TemporaryDirectory[str] | None = None
        if credential and credential.get("auth_json"):
            temporary = tempfile.TemporaryDirectory(prefix="ai-usage-codex-")
            auth_file = Path(temporary.name) / "auth.json"
            auth_file.write_text(json.dumps(credential["auth_json"]), encoding="utf-8")
            auth_file.chmod(0o600)
            profile_dir = temporary.name
        # end if
        if profile_dir:
            environment["CODEX_HOME"] = str(Path(profile_dir).expanduser())
        # end if
        observed = datetime.now(UTC)
        try:
            async with AppServerClient(
                str(account.options.get("command", "codex")), environment
            ) as client:
                await client.request("account/read", {"refreshToken": True})
                result = await client.request("account/rateLimits/read")
            # end with
        except FileNotFoundError as exception:
            raise ProviderError("Codex CLI was not found") from exception
        finally:
            if temporary is not None:
                temporary.cleanup()
            # end if
        # end try
        return ProviderFetchResult(
            service=self.service,
            provider=self.key,
            account_id=account.id,
            fetched_at=observed,
            metrics=parse_rate_limits(result, observed),
        )
    # end def
# end class


def parse_codex_status(output: str, observed_at: datetime) -> list[Metric]:
    model = codex_model(output)
    metrics: list[Metric] = []
    for match in STATUS_PATTERN.finditer(output):
        name = match.group("name").lower().replace(" ", "-")
        key = "seven-days" if name == "weekly" else f"{name}s"
        remaining = float(match.group("remaining"))
        metrics.append(
            Metric(
                key=key,
                name=match.group("name"),
                usage=Usage(percentage=100 - remaining),
                observed_at=observed_at,
                model=model,
                metadata={"reset_text": match.group("reset")},
            )
        )
    # end for
    return metrics
# end def


class CodexStatusProvider(Provider):
    service = "codex"
    key = "cli-status"
    display_name = "Codex /status"
    icon = IconRef(set="solid", name="terminal")
    configuration_fields = (
        ConfigurationField(key="command", label="Codex executable", default="codex"),
    )

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        del credential
        observed = datetime.now(UTC)
        output = await run_codex_status(str(account.options.get("command", "codex")))
        metrics = parse_codex_status(output, observed)
        if not metrics:
            raise ProviderError("Codex /status output did not contain usage limits")
        # end if
        is_stale = STALE_WARNING_PATTERN.search(output) is not None
        return ProviderFetchResult(
            service=self.service,
            provider=self.key,
            account_id=account.id,
            fetched_at=observed,
            status=FetchStatus.STALE if is_stale else FetchStatus.SUCCESS,
            error="codex reported limits may be stale" if is_stale else None,
            metrics=metrics,
            notes=extract_codex_notes(output),
        )
    # end def
# end class


async def run_codex_status(command: str) -> str:
    def run_terminal() -> str:
        import pexpect

        child = pexpect.spawn(command, encoding="utf-8", timeout=30)
        child.sendline("/status")
        child.expect("Weekly limit|hour limit", timeout=30)
        child.sendline("/status")
        child.expect("Weekly limit|hour limit", timeout=30)
        child.sendline("/quit")
        child.expect(pexpect.EOF, timeout=10)
        return child.before
    # end def

    return await asyncio.to_thread(run_terminal)
# end def

