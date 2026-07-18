"""Idempotent shell tab-completion installation."""

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

import click
from click.shell_completion import get_completion_class

from ai_usage.settings import Paths

PROG_NAME = "ai-usage"
COMPLETE_VAR = "_AI_USAGE_COMPLETE"

RC_FILES = {
    "bash": "~/.bashrc",
    "zsh": "~/.zshrc",
}

SHELLS = ("bash", "zsh", "fish")
HASH_MARKER_PREFIX = "# ai-usage-completion-hash: "
HASH_MARKER_PATTERN = re.compile(re.escape(HASH_MARKER_PREFIX) + r"([0-9a-f]{64})")


def hash_script(script: str) -> str:
    return hashlib.sha256(script.encode("utf-8")).hexdigest()
# end def


def completion_script_path(paths: Paths, shell: str) -> Path:
    if shell == "fish":
        return Path("~/.config/fish/completions/ai-usage.fish").expanduser()
    # end if
    return paths.root / "completions" / f"ai-usage.{shell}"
# end def


def installed_completion_shells(paths: Paths) -> list[str]:
    return [shell for shell in SHELLS if completion_script_path(paths, shell).exists()]
# end def


def installed_completion_hash(paths: Paths, shell: str) -> str | None:
    path = completion_script_path(paths, shell)
    if not path.exists():
        return None
    # end if
    match = HASH_MARKER_PATTERN.search(path.read_text(encoding="utf-8"))
    return match.group(1) if match else None
# end def


@dataclass(frozen=True, slots=True)
class CompletionResult:
    shell: str
    script_path: Path
    rc_path: Path | None
# end class


def detect_shell() -> str:
    shell_path = os.environ.get("SHELL", "")
    name = Path(shell_path).name
    if name in ("bash", "zsh", "fish"):
        return name
    # end if
    return "bash"
# end def


def render_script(main: click.BaseCommand, shell: str) -> str:
    completion_class = get_completion_class(shell)
    if completion_class is None:
        raise click.ClickException(f"unsupported shell: {shell}")
    # end if
    completion = completion_class(main, {}, PROG_NAME, COMPLETE_VAR)
    return completion.source()
# end def


def install_completion(paths: Paths, main: click.BaseCommand, shell: str | None) -> CompletionResult:
    resolved_shell = shell or detect_shell()
    script = render_script(main, resolved_shell)
    tagged_script = f"{HASH_MARKER_PREFIX}{hash_script(script)}\n{script}"

    if resolved_shell == "fish":
        script_path = completion_script_path(paths, resolved_shell)
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(tagged_script, encoding="utf-8")
        return CompletionResult(shell=resolved_shell, script_path=script_path, rc_path=None)
    # end if

    if resolved_shell not in RC_FILES:
        raise click.ClickException(f"unsupported shell: {resolved_shell}")
    # end if

    script_path = completion_script_path(paths, resolved_shell)
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(tagged_script, encoding="utf-8")

    rc_path = Path(RC_FILES[resolved_shell]).expanduser()
    source_line = f"source '{script_path}'"
    rc_text = rc_path.read_text(encoding="utf-8") if rc_path.exists() else ""
    if source_line not in rc_text:
        with rc_path.open("a", encoding="utf-8") as handle:
            if rc_text and not rc_text.endswith("\n"):
                handle.write("\n")
            # end if
            handle.write(f"{source_line}\n")
        # end with
    # end if

    return CompletionResult(shell=resolved_shell, script_path=script_path, rc_path=rc_path)
# end def
