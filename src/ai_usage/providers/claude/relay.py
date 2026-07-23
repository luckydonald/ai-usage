"""Installs/removes the Claude Code statusLine relay script that mirrors /usage payloads to disk."""

import json
import shlex
import sys
from pathlib import Path
from typing import Any

from ai_usage.models import AccountConfig
from ai_usage.providers.claude_cli import claude_profile_path


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
