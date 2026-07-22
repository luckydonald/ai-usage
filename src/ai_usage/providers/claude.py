"""Claude status-line ingestion and /usage provider."""

import asyncio
import hashlib
import json
import logging
import os
import re
import shlex
import sys
import time
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
from ai_usage.providers.base import (
    ConfigurationField,
    DiscoveredAccount,
    Provider,
    ProviderError,
)
from ai_usage.webview_login import capture_cookies_via_webview

LOGGER = logging.getLogger(__name__)

AUTH_ERROR_STATUS_CODES = frozenset({401, 403})


def reauth_hint(account_id: str) -> str:
    return f"re-authenticate with: ai-usage provider login --account {account_id}"
# end def


def describe_fetch_failure(exception: Exception, account_id: str) -> str:
    """Append a re-auth hint when an exception looks like an expired/blocked session."""
    response = getattr(exception, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code in AUTH_ERROR_STATUS_CODES:
        return f"{exception} — session likely expired or blocked; {reauth_hint(account_id)}"
    # end if
    return str(exception)
# end def


async def get_json(
    client: AsyncSession,
    path: str,
    account_id: str,
    params: dict[str, Any] | None = None,
) -> Any:
    """GET a Claude endpoint, logging the outgoing request and raising a labeled error on failure."""
    LOGGER.debug("GET %s params=%s", path, params)
    response = await client.get(path, params=params)
    if response.status_code >= 400:
        exception = RuntimeError(f"HTTP Error {response.status_code}")
        exception.response = response
        raise ProviderError(
            f"GET {path} failed: {describe_fetch_failure(exception, account_id)}"
        )
    # end if
    return response.json()
# end def


ANSI_PATTERN = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
SECTION_PATTERN = re.compile(
    r"(?P<name>Current session|Current week \(all models\)|Current week \([^)]+\))"
    r".*?(?P<percentage>\d+(?:\.\d+)?)%\s+used.*?Resets\s+(?P<reset>[^\r\n]+)",
    re.IGNORECASE | re.DOTALL,
)
PROMO_PATTERN = re.compile(r"^\s*\+\d+%.*promo.*$", re.IGNORECASE | re.MULTILINE)
SETUP_TEXT_STYLE_PATTERN = re.compile(r"Choose\s+the\s+text\s+style", re.IGNORECASE)
CLAUDE_ERROR_LOG_DIR = Path("/tmp/ai-usage/errors")


def claude_default_profile() -> Path:
    return Path.home() / ".claude"
# end def


def claude_profile_path(profile_dir: str | None) -> Path:
    return Path(profile_dir).expanduser() if profile_dir else claude_default_profile()
# end def


def canonical_claude_profile_dir(profile_dir: str | None) -> str | None:
    """Return an override only when the profile is not Claude's native default."""
    profile = claude_profile_path(profile_dir)
    if profile.resolve() == claude_default_profile().resolve():
        return None
    # end if
    return str(profile)
# end def


def extract_claude_notes(output: str) -> list[str]:
    clean = ANSI_PATTERN.sub("", output).replace("\r", "")
    return [match.group(0).strip() for match in PROMO_PATTERN.finditer(clean)]
# end def


def claude_setup_required_message(
    output: str | None,
    command: str,
    profile_dir: str | None,
) -> str | None:
    """Explain how to complete Claude's first-run text-style selection."""
    clean = ANSI_PATTERN.sub(" ", output or "").replace("\r", "")
    if not SETUP_TEXT_STYLE_PATTERN.search(clean):
        return None
    # end if
    config_dir = canonical_claude_profile_dir(profile_dir)
    if config_dir:
        interactive_command = f"CLAUDE_CONFIG_DIR={shlex.quote(config_dir)} {shlex.quote(command)}"
        profile = config_dir
    else:
        profile = "the default Claude profile"
        interactive_command = shlex.quote(command)
    # end if
    return (
        f"Claude is waiting for first-run setup in {profile}; run "
        f"{interactive_command} interactively, choose a text style, then retry the crawl."
    )
# end def


def write_claude_error_log(output: str) -> Path:
    """Persist a failed Claude CLI transcript under a content-addressed temporary path."""
    digest = hashlib.sha256(output.encode("utf-8")).hexdigest()
    path = CLAUDE_ERROR_LOG_DIR / f"claude-cli.{digest}.log"
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not path.exists():
        temporary = path.with_suffix(".tmp")
        temporary.write_text(output, encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(path)
    # end if
    return path
# end def


def claude_cli_failure_message(output: str, command: str, profile_dir: str | None) -> str:
    """Persist Claude CLI failures and return the most actionable error message."""
    if output:
        error_log = write_claude_error_log(output)
        LOGGER.error("Saved Claude CLI transcript to %s", error_log)
    # end if
    setup_message = claude_setup_required_message(output, command, profile_dir)
    if setup_message:
        return setup_message
    # end if
    return "Claude /usage did not become ready; use Claude once to refresh the status relay"
# end def


# The claude.ai web app's promo banner ("Your limits are temporarily boosted...") isn't part
# of any documented API — it's a GrowthBook remote-config feature flag fetched via the web
# app's own bootstrap endpoint. `19186470` is that flag's key (a djb2 hash of its real,
# unpublished name); hardcoded since there's no way to derive or verify it other than by its
# distinctive content (see ai/plans/009_fix-the-chart-s-remount-reanimate-bug-add-a-real-vertical-sl.md
# for how this was found, and why it can't be resolved dynamically).
CLAUDE_WEB_PROMO_FEATURE_KEY = "19186470"


def extract_claude_web_notes(app_start_payload: dict[str, Any]) -> list[str]:
    features = app_start_payload.get("org_growthbook", {}).get("features", {})
    feature = features.get(CLAUDE_WEB_PROMO_FEATURE_KEY)
    if not isinstance(feature, dict):
        return []
    # end if
    default_value = feature.get("defaultValue")
    if not isinstance(default_value, dict):
        return []
    # end if
    text = default_value.get("en-US") or next(iter(default_value.values()), None)
    return [text] if isinstance(text, str) and text else []
# end def


def claude_metric_key(name: str) -> str:
    normalized = name.casefold()
    if "session" in normalized:
        return "five-hours"
    elif "all models" in normalized:
        return "seven-days"
    # end if
    model = normalized.split("(", 1)[-1].rstrip(")")
    return "seven-days-" + re.sub(r"[^a-z0-9]+", "-", model).strip("-")
# end def


def claude_metric_model(name: str) -> str | None:
    """Extract the model name from a per-model section title, e.g. `Current week (Fable)` -> `Fable`."""
    normalized = name.casefold()
    if "session" in normalized or "all models" in normalized:
        return None
    # end if
    if "(" not in name or not name.endswith(")"):
        return None
    # end if
    return name.split("(", 1)[-1].rstrip(")").strip() or None
# end def


def parse_status_payload(payload: dict[str, Any], observed_at: datetime) -> list[Metric]:
    limits = payload.get("rate_limits") or {}
    metrics: list[Metric] = []
    for source_key, metric_key, name, seconds in (
        ("five_hour", "five-hours", "Five hours", 5 * 3600),
        ("seven_day", "seven-days", "Seven days", 7 * 86400),
    ):
        window = limits.get(source_key)
        if not window:
            continue
        # end if
        metrics.append(
            Metric(
                key=metric_key,
                name=name,
                usage=Usage(percentage=float(window["used_percentage"])),
                observed_at=observed_at,
                reset_at=datetime.fromtimestamp(int(window["resets_at"]), UTC),
                window_seconds=seconds,
            )
        )
    # end for
    return metrics
# end def


def parse_usage_output(output: str, observed_at: datetime) -> list[Metric]:
    clean = ANSI_PATTERN.sub("", output).replace("\r", "")
    metrics: list[Metric] = []
    for match in SECTION_PATTERN.finditer(clean):
        name = " ".join(match.group("name").split())
        metrics.append(
            Metric(
                key=claude_metric_key(name),
                name=name,
                usage=Usage(percentage=float(match.group("percentage"))),
                observed_at=observed_at,
                model=claude_metric_model(name),
                metadata={"reset_text": match.group("reset").strip()},
            )
        )
    # end for
    return metrics
# end def


class ClaudeUsageWindowPayload(BaseModel):
    utilization: float | None = None
    resets_at: datetime | None = None
# end class


class ClaudeUsagePayload(BaseModel):
    five_hour: ClaudeUsageWindowPayload | None = None
    seven_day: ClaudeUsageWindowPayload | None = None
# end class


class ClaudeOrganizationPayload(BaseModel):
    uuid: str
    name: str | None = None
    billing_type: str | None = None
# end class


class ClaudeAccountPayload(BaseModel):
    email_address: str | None = None
    full_name: str | None = None
# end class


class ClaudeSubscriptionStatusPayload(BaseModel):
    status: str | None = None
    cancel_at_ts: datetime | None = None
# end class


def parse_claude_web_usage(payload: dict[str, Any], observed_at: datetime) -> list[Metric]:
    try:
        windows = ClaudeUsagePayload.model_validate(payload)
    except ValidationError as exception:
        LOGGER.warning(
            "Claude usage payload did not match the expected schema, falling back to raw "
            "field access: %s",
            exception,
        )
        windows = None
    # end try
    metrics: list[Metric] = []
    for source_key, metric_key, name, seconds in (
        ("five_hour", "five-hours", "Five hours", 5 * 3600),
        ("seven_day", "seven-days", "Seven days", 7 * 86400),
    ):
        try:
            if windows is not None:
                window = getattr(windows, source_key)
                utilization = window.utilization if window else None
                reset_at = window.resets_at if window else None
            else:
                raw_window = payload.get(source_key)
                raw_window = raw_window if isinstance(raw_window, dict) else {}
                utilization = raw_window.get("utilization")
                reset_text = raw_window.get("resets_at")
                reset_at = (
                    datetime.fromisoformat(reset_text) if isinstance(reset_text, str) else None
                )
            # end if
            if not isinstance(utilization, int | float):
                continue
            # end if
            metrics.append(
                Metric(
                    key=metric_key,
                    name=name,
                    usage=Usage(percentage=float(utilization)),
                    observed_at=observed_at,
                    reset_at=reset_at,
                    window_seconds=seconds,
                )
            )
        except (ValueError, TypeError) as exception:
            LOGGER.warning("could not parse Claude %s usage window: %s", source_key, exception)
        # end try
    # end for
    return metrics
# end def


class ClaudeWebUsageProvider(Provider):
    service = "claude"
    key = "web"
    display_name = "Claude private web API"
    icon = IconRef(set="solid", name="globe")
    configuration_fields = (
        ConfigurationField(
            key="org_id",
            label="Claude organization UUID",
            help="Auto-detected after login when the account belongs to a single organization.",
        ),
    )
    login_url = "https://claude.ai/login"

    async def authenticate(self, options: dict[str, Any]) -> dict[str, Any] | None:
        del options
        # pywebview must run on the main thread (it raises WebViewException otherwise), so this
        # is a deliberate synchronous, blocking call rather than `asyncio.to_thread(...)`.
        cookies = capture_cookies_via_webview(self.login_url, self.display_name)
        return {"cookies": cookies} if cookies else None
    # end def

    async def discover_options(self, credential: dict[str, Any] | None) -> dict[str, Any]:
        cookies = (credential or {}).get("cookies") or {}
        if not cookies:
            LOGGER.warning("could not auto-detect Claude organization: no cookies were captured")
            return {}
        # end if
        try:
            # claude.ai sits behind Cloudflare (see CodexWebUsageProvider for the full story) —
            # impersonate a real Chrome TLS fingerprint so cf_clearance is honored.
            async with AsyncSession(
                timeout=20, cookies=cookies, base_url="https://claude.ai", impersonate="chrome",
            ) as client:
                response = await client.get("/api/organizations")
                response.raise_for_status()
                organizations = response.json()
            # end async with
        except Exception as exception:  # noqa: BLE001
            LOGGER.warning("could not auto-detect Claude organization: %s", exception)
            return {}
        # end try
        if not organizations:
            LOGGER.warning(
                "could not auto-detect Claude organization: /api/organizations returned no "
                "organizations for the captured cookies (%d cookie(s): %s)",
                len(cookies),
                ", ".join(sorted(cookies)),
            )
            return {}
        # end if
        if len(organizations) > 1:
            LOGGER.warning(
                "found %d Claude organizations, defaulting to the first (%s); pass --org-id "
                "explicitly to pick a different one (%s)",
                len(organizations),
                organizations[0].get("name"),
                ", ".join(f"{org.get('name')}={org.get('uuid')}" for org in organizations),
            )
        # end if
        return {"org_id": organizations[0]["uuid"]}
    # end def

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        org_id = str(account.options.get("org_id") or "")
        if not org_id:
            raise ProviderError("Claude web provider requires an 'org_id' option")
        # end if
        cookies = (credential or {}).get("cookies", {})
        headers = (credential or {}).get("headers", {})
        observed = datetime.now(UTC)
        raw_payload: dict[str, Any] = {}
        async with AsyncSession(
            timeout=20, cookies=cookies, headers=headers, base_url="https://claude.ai",
            impersonate="chrome",
        ) as client:
            usage_payload = await get_json(client, f"/api/organizations/{org_id}/usage", account.id)
            raw_payload["usage"] = usage_payload
            metrics = parse_claude_web_usage(usage_payload, observed)
            if not metrics:
                raise ProviderError("Claude usage response did not contain any usage windows")
            # end if

            organization: ClaudeOrganizationPayload | None = None
            try:
                organizations_payload = await get_json(client, "/api/organizations", account.id)
                raw_payload["organizations"] = organizations_payload
                match = next(
                    (org for org in organizations_payload if org.get("uuid") == org_id), None
                )
                organization = (
                    ClaudeOrganizationPayload.model_validate(match) if match is not None else None
                )
            except Exception as exception:  # noqa: BLE001
                LOGGER.warning(
                    "could not fetch Claude organization info: %s",
                    describe_fetch_failure(exception, account.id),
                )
            # end try

            account_info: ClaudeAccountPayload | None = None
            try:
                account_payload = await get_json(client, "/api/account", account.id)
                raw_payload["account"] = account_payload
                account_info = ClaudeAccountPayload.model_validate(account_payload)
            except Exception as exception:  # noqa: BLE001
                LOGGER.warning(
                    "could not fetch Claude account info: %s",
                    describe_fetch_failure(exception, account.id),
                )
            # end try

            subscription_info: ClaudeSubscriptionStatusPayload | None = None
            try:
                status_payload = await get_json(
                    client, f"/api/organizations/{org_id}/subscription_status", account.id
                )
                raw_payload["subscription_status"] = status_payload
                subscription_info = ClaudeSubscriptionStatusPayload.model_validate(status_payload)
            except Exception as exception:  # noqa: BLE001
                LOGGER.warning(
                    "could not fetch Claude subscription status: %s",
                    describe_fetch_failure(exception, account.id),
                )
            # end try

            notes: list[str] = []
            try:
                app_start_payload = await get_json(
                    client,
                    f"/edge-api/bootstrap/{org_id}/app_start",
                    account.id,
                    params={
                        "statsig_hashing_algorithm": "djb2",
                        "growthbook_format": "sdk",
                        "include_system_prompts": "false",
                    },
                )
                raw_payload["app_start"] = app_start_payload
                notes = extract_claude_web_notes(app_start_payload)
            except Exception as exception:  # noqa: BLE001
                LOGGER.warning(
                    "could not fetch Claude app_start bootstrap: %s",
                    describe_fetch_failure(exception, account.id),
                )
            # end try
        # end with

        identity = None
        if organization is not None or account_info is not None:
            identity = AccountIdentity(
                name=organization.name if organization is not None else None,
                email=account_info.email_address if account_info is not None else None,
            )
        # end if
        subscription = None
        if organization is not None or subscription_info is not None:
            subscription = SubscriptionStatus(
                plan_type=organization.billing_type if organization is not None else None,
                status=subscription_info.status if subscription_info is not None else None,
                cancel_at=subscription_info.cancel_at_ts if subscription_info is not None else None,
            )
        # end if
        return ProviderFetchResult(
            service=self.service,
            provider=self.key,
            account_id=account.id,
            fetched_at=observed,
            metrics=metrics,
            identity=identity,
            subscription=subscription,
            raw_payload=raw_payload,
            notes=notes,
        )
    # end def
# end class


class ClaudeStatusProvider(Provider):
    service = "claude"
    key = "statusline"
    display_name = "Claude status line with /usage fallback"
    icon = IconRef(set="solid", name="gauge")
    configuration_fields = (
        ConfigurationField(key="command", label="Claude executable", default="claude"),
        ConfigurationField(key="profile_dir", label="Claude profile", kind="path"),
        ConfigurationField(key="relay_file", label="Status relay file", kind="path"),
        ConfigurationField(key="stale_seconds", label="Relay staleness", kind="integer", default=120),
    )

    async def discover(self) -> list[DiscoveredAccount]:
        settings = Path.home() / ".claude" / "settings.json"
        if settings.exists():
            return [DiscoveredAccount(name="Claude", options={"profile_dir": str(settings.parent)})]
        # end if
        return []
    # end def

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        del credential
        observed = datetime.now(UTC)
        relay_file_value = account.options.get("relay_file")
        if relay_file_value:
            relay_file = Path(str(relay_file_value)).expanduser()
            stale_seconds = int(account.options.get("stale_seconds", 120))
            if relay_file.exists():
                age = time.time() - relay_file.stat().st_mtime
                if age <= stale_seconds:
                    payload = json.loads(relay_file.read_text(encoding="utf-8"))
                    metrics = parse_status_payload(payload, observed)
                    if metrics:
                        return ProviderFetchResult(
                            service=self.service,
                            provider=self.key,
                            account_id=account.id,
                            fetched_at=observed,
                            status=FetchStatus.SUCCESS,
                            metrics=metrics,
                        )
                    # end if
                # end if
                # relay data missing or stale: fall through and ask the CLI directly instead
                # of surfacing outdated numbers.
            # end if
        # end if
        output = await run_claude_usage(
            str(account.options.get("command", "claude")),
            str(account.options["profile_dir"]) if account.options.get("profile_dir") else None,
        )
        metrics = parse_usage_output(output, observed)
        if not metrics:
            raise ProviderError("Claude /usage output did not contain recognized usage sections")
        # end if
        return ProviderFetchResult(
            service=self.service,
            provider=self.key,
            account_id=account.id,
            fetched_at=observed,
            metrics=metrics,
            notes=extract_claude_notes(output),
        )
    # end def
# end class


class ClaudeUsageProvider(ClaudeStatusProvider):
    key = "cli-usage"
    display_name = "Claude /usage"
    icon = IconRef(set="solid", name="terminal")

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        options = dict(account.options)
        options.pop("relay_file", None)
        direct = account.model_copy(update={"options": options})
        return await super().fetch(direct, credential)
    # end def
# end class


async def run_claude_usage(command: str, profile_dir: str | None) -> str:
    def run_terminal() -> str:
        import pexpect

        environment = dict(os.environ)
        config_dir = canonical_claude_profile_dir(profile_dir)
        if config_dir:
            environment["CLAUDE_CONFIG_DIR"] = config_dir
        # end if
        child = pexpect.spawn(command, encoding="utf-8", timeout=30, env=environment)
        try:
            child.sendline("/usage")
            child.expect("Current session", timeout=30)
            time.sleep(1)
            child.sendline("/exit")
            child.expect(pexpect.EOF, timeout=10)
            return child.before
        except (pexpect.TIMEOUT, pexpect.EOF) as exception:
            raise ProviderError(
                claude_cli_failure_message(child.before or "", command, profile_dir)
            ) from exception
        finally:
            if child.isalive():
                child.close(force=True)
            # end if
        # end try
    # end def

    return await asyncio.to_thread(run_terminal)
# end def


def write_relay_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
# end def


def install_status_relay(account: AccountConfig, local_root: Path) -> Path:
    profile = claude_profile_path(
        str(account.options["profile_dir"]) if account.options.get("profile_dir") else None
    )
    settings_path = profile / "settings.json"
    profile.mkdir(mode=0o700, parents=True, exist_ok=True)
    settings: dict[str, Any] = {}
    if settings_path.exists():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    # end if
    existing = settings.get("statusLine")
    marker = f"ai-usage-relay-{account.id}"
    if isinstance(existing, dict) and marker in str(existing.get("command", "")):
        return settings_path
    # end if
    relay_root = local_root / "claude-relay"
    relay_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    original_path = relay_root / f"{account.id}.original.json"
    original_path.write_text(json.dumps(existing), encoding="utf-8")
    original_path.chmod(0o600)
    script_path = relay_root / f"{marker}.py"
    relay_file = local_root / "relay" / f"{account.id}.json"
    original_command = existing.get("command") if isinstance(existing, dict) else None
    script = f"""#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

payload = sys.stdin.buffer.read()
target = Path({str(relay_file)!r})
target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
temporary = target.with_suffix('.tmp')
temporary.write_bytes(payload)
temporary.chmod(0o600)
temporary.replace(target)
command = {original_command!r}
if command:
    result = subprocess.run(command, input=payload, shell=True, capture_output=True)
    sys.stdout.buffer.write(result.stdout)
    sys.stderr.buffer.write(result.stderr)
    raise SystemExit(result.returncode)
"""
    script_path.write_text(script, encoding="utf-8")
    script_path.chmod(0o700)
    settings["statusLine"] = {
        "type": "command",
        "command": f"{shlex.quote(sys.executable)} {shlex.quote(str(script_path))} # {marker}",
    }
    temporary_settings = settings_path.with_suffix(".tmp")
    temporary_settings.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    temporary_settings.chmod(0o600)
    temporary_settings.replace(settings_path)
    return settings_path
# end def


def remove_status_relay(account: AccountConfig, local_root: Path) -> None:
    profile = claude_profile_path(
        str(account.options["profile_dir"]) if account.options.get("profile_dir") else None
    )
    settings_path = profile / "settings.json"
    marker = f"ai-usage-relay-{account.id}"
    relay_root = local_root / "claude-relay"
    original_path = relay_root / f"{account.id}.original.json"
    script_path = relay_root / f"{marker}.py"
    relay_file = local_root / "relay" / f"{account.id}.json"
    if settings_path.exists():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        current = settings.get("statusLine")
        if isinstance(current, dict) and marker in str(current.get("command", "")):
            original = (
                json.loads(original_path.read_text(encoding="utf-8"))
                if original_path.exists()
                else None
            )
            if original is None:
                settings.pop("statusLine", None)
            else:
                settings["statusLine"] = original
            # end if
            temporary = settings_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
            temporary.replace(settings_path)
        # end if
    # end if
    for path in (script_path, original_path, relay_file):
        if path.exists():
            path.unlink()
        # end if
    # end for
# end def
