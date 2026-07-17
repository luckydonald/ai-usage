import plistlib

from ai_usage.services import SERVICE_MARKER, launchd_plist, systemd_unit
from tests.test_storage import temporary_paths


def test_systemd_unit_has_marker_and_command() -> None:
    unit = systemd_unit("/venv/bin/ai-usage", ["run-all", "--port", "4458"])
    assert SERVICE_MARKER in unit
    assert "ExecStart=/venv/bin/ai-usage run-all --port 4458" in unit
# end def


def test_launchd_plist_has_marker(tmp_path) -> None:
    payload = plistlib.loads(
        launchd_plist("/venv/bin/ai-usage", ["crawl"], temporary_paths(tmp_path))
    )
    assert payload["AIUsageMarker"] == SERVICE_MARKER
    assert payload["ProgramArguments"][-1] == "crawl"
# end def

