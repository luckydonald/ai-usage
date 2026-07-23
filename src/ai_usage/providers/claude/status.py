"""Claude status-line ingestion and `/usage` fallback provider."""

import json
import logging
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_usage.icons import IconRef
from ai_usage.models import FetchStatus, Metric, ProviderFetchResult, Usage
from ai_usage.models import AccountConfig
from ai_usage.providers.base import ConfigurationField, DiscoveredAccount, Provider, ProviderError, ProviderLoginError
from ai_usage.providers.claude_direct import run_claude_usage_direct
from ai_usage.providers.claude_interactive import run_claude_usage

LOGGER = logging.getLogger(__name__)

ANSI_PATTERN = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
SECTION_PATTERN = re.compile(
    r"(?P<name>Current session|Current week \(all models\)|Current week \([^)]+\))"
    r".*?(?P<percentage>\d+(?:\.\d+)?)%\s+used.*?Resets\s+(?P<reset>[^\r\n]+)",
    re.IGNORECASE | re.DOTALL,
)
PROMO_PATTERN = re.compile(r"^\s*\+\d+%.*promo.*$", re.IGNORECASE | re.MULTILINE)


def extract_claude_notes(output: str) -> list[str]:
    clean = normalize_claude_terminal_output(output)
    return [match.group(0).strip() for match in PROMO_PATTERN.finditer(clean)]
# end def


def normalize_claude_terminal_output(output: str) -> str:
    """Replace terminal controls with spacing so cursor-positioned words stay separate."""
    return ANSI_PATTERN.sub(" ", output).replace("\r", "")
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
    clean = normalize_claude_terminal_output(output)
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

    def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
        del account, result
        raise ProviderLoginError(f"{self.display_name} cannot determine the account login")
    # end def

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
        command = str(account.options.get("command", "claude"))
        profile_dir = str(account.options["profile_dir"]) if account.options.get("profile_dir") else None
        direct_output = await run_claude_usage_direct(command, profile_dir)
        output = direct_output or ""
        metrics = parse_usage_output(output, observed)
        if not metrics:
            output = await run_claude_usage(command, profile_dir)
            metrics = parse_usage_output(output, observed)
        # end if
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
