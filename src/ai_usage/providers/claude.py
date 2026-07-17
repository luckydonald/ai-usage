"""Claude status-line ingestion and /usage provider."""

import asyncio
import json
import os
import re
import shlex
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_usage.models import AccountConfig, FetchStatus, Metric, ProviderFetchResult, Usage
from ai_usage.providers.base import (
    ConfigurationField,
    DiscoveredAccount,
    Provider,
    ProviderError,
)

ANSI_PATTERN = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
SECTION_PATTERN = re.compile(
    r"(?P<name>Current session|Current week \(all models\)|Current week \([^)]+\))"
    r".*?(?P<percentage>\d+(?:\.\d+)?)%\s+used.*?Resets\s+(?P<reset>[^\r\n]+)",
    re.IGNORECASE | re.DOTALL,
)


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
                payload = json.loads(relay_file.read_text(encoding="utf-8"))
                metrics = parse_status_payload(payload, observed)
                if metrics:
                    return ProviderFetchResult(
                        service=self.service,
                        provider=self.key,
                        account_id=account.id,
                        fetched_at=observed,
                        status=FetchStatus.SUCCESS if age <= stale_seconds else FetchStatus.STALE,
                        metrics=metrics,
                        error=(
                            None
                            if age <= stale_seconds
                            else f"no new statusline data yet (last update {age:.0f}s ago)"
                        ),
                    )
                # end if
            # end if
        # end if
        output = await run_claude_usage(
            str(account.options.get("command", "claude")),
            str(account.options.get("profile_dir", "")) or None,
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
        )
    # end def
# end class


class ClaudeUsageProvider(ClaudeStatusProvider):
    key = "cli-usage"
    display_name = "Claude /usage"

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
        if profile_dir:
            environment["CLAUDE_CONFIG_DIR"] = str(Path(profile_dir).expanduser())
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
                "Claude /usage did not become ready; use Claude once to refresh the status relay"
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
    profile = Path(str(account.options.get("profile_dir", Path.home() / ".claude"))).expanduser()
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
    profile = Path(str(account.options.get("profile_dir", Path.home() / ".claude"))).expanduser()
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
