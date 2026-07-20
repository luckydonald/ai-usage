"""Change-only storage for special events/notes (promo banners, limit-reset hints, ...).

Unlike the metric-keyed history tree, notes are not observed on a fixed schedule with a
window — they are simply "active" or not on any given crawl. Only transitions (a note
appearing or disappearing) are appended, so the store stays small even when crawling
every second.
"""

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ai_usage.settings import Paths


@dataclass(frozen=True, slots=True)
class NoteTransition:
    observed_at: datetime
    text: str
    active: bool
# end class


@dataclass(frozen=True, slots=True)
class NoteRange:
    service: str
    account_id: str
    text: str
    start: datetime
    end: datetime | None
# end class


def collect_note_ranges(paths: Paths) -> list[NoteRange]:
    """Replay every recorded transition into start/end ranges (`end=None` while still active)."""
    root = paths.local / "notes"
    if not root.exists():
        return []
    # end if
    ranges: list[NoteRange] = []
    for path in sorted(root.glob("*/*.jsonl")):
        service = path.parent.name
        account_id = path.stem
        open_starts: dict[str, datetime] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            # end if
            record = json.loads(line)
            observed_at = datetime.fromisoformat(record["observed_at"])
            text = record["text"]
            if record["active"]:
                open_starts[text] = observed_at
            else:
                start = open_starts.pop(text, observed_at)
                ranges.append(
                    NoteRange(
                        service=service,
                        account_id=account_id,
                        text=text,
                        start=start,
                        end=observed_at,
                    )
                )
            # end if
        # end for
        for text, start in open_starts.items():
            ranges.append(
                NoteRange(service=service, account_id=account_id, text=text, start=start, end=None)
            )
        # end for
    # end for
    return ranges
# end def


class NotesStore:
    def __init__(self, paths: Paths):
        self.paths = paths
    # end def

    def note_path(self, service: str, account_id: str) -> Path:
        return self.paths.local / "notes" / service / f"{account_id}.jsonl"
    # end def

    def load_active_notes(self, service: str, account_id: str) -> set[str]:
        path = self.note_path(service, account_id)
        if not path.exists():
            return set()
        # end if
        active: set[str] = set()
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            # end if
            record = json.loads(line)
            if record["active"]:
                active.add(record["text"])
            else:
                active.discard(record["text"])
            # end if
        # end for
        return active
    # end def

    def record_transitions(
        self,
        service: str,
        account_id: str,
        transitions: list[NoteTransition],
    ) -> None:
        if not transitions:
            return
        # end if
        path = self.note_path(service, account_id)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
            for transition in transitions:
                payload = {
                    "observed_at": transition.observed_at.astimezone(UTC).isoformat(),
                    "text": transition.text,
                    "active": transition.active,
                }
                stream.write(json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n")
            # end for
            stream.flush()
            os.fsync(stream.fileno())
        # end with
    # end def

    def diff_and_record(
        self,
        service: str,
        account_id: str,
        current_notes: list[str],
        known_active: set[str],
        observed_at: datetime,
    ) -> tuple[set[str], list[NoteTransition]]:
        """Compare `current_notes` against `known_active`, persist only the delta, and
        return the updated active set plus the transitions that were recorded (for reporting)."""
        current = set(current_notes)
        transitions = [
            NoteTransition(observed_at=observed_at, text=text, active=True)
            for text in sorted(current - known_active)
        ]
        transitions += [
            NoteTransition(observed_at=observed_at, text=text, active=False)
            for text in sorted(known_active - current)
        ]
        self.record_transitions(service, account_id, transitions)
        return current, transitions
    # end def
# end class
