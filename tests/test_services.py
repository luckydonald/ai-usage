import plistlib
from types import SimpleNamespace

from ai_usage.services import linux, macos, windows
from ai_usage.services.linux import SERVICE_MARKER
from tests.test_storage import temporary_paths


def test_systemd_unit_has_marker_and_command() -> None:
    payload = linux.unit("/venv/bin/ai-usage", ["up", "--port", "4458"])
    assert SERVICE_MARKER in payload
    assert "ExecStart=/venv/bin/ai-usage up --port 4458" in payload
# end def


def test_launchd_plist_has_marker(tmp_path) -> None:
    payload = plistlib.loads(
        macos.plist("/venv/bin/ai-usage", ["crawl"], temporary_paths(tmp_path).logs)
    )
    assert payload["AIUsageMarker"] == SERVICE_MARKER
    assert payload["ProgramArguments"][-1] == "crawl"
# end def


def test_linux_install_status_and_uninstall(tmp_path, monkeypatch) -> None:
    target = tmp_path / "ai-usage.service"
    calls: list[list[str]] = []
    monkeypatch.setattr(linux, "target_path", lambda: target)
    monkeypatch.setattr(linux.subprocess, "run", lambda arguments, **kwargs: calls.append(arguments) or SimpleNamespace(returncode=0))

    linux.install("/venv/bin/ai-usage", ["crawl"])
    status = linux.status()
    linux.uninstall()

    assert status.installed and status.mode == "crawler"
    assert not target.exists()
    assert ["systemctl", "--user", "enable", "--now", "ai-usage.service"] in calls
# end def


def test_macos_install_status_and_uninstall(tmp_path, monkeypatch) -> None:
    target = tmp_path / "ai-usage.plist"
    monkeypatch.setattr(macos, "target_path", lambda: target)
    monkeypatch.setattr(macos.subprocess, "run", lambda arguments, **kwargs: SimpleNamespace(returncode=0))

    macos.install("/venv/bin/ai-usage", ["serve"], tmp_path)
    status = macos.status()
    macos.uninstall()

    assert status.installed and status.mode == "webserver"
    assert not target.exists()
# end def


def test_windows_install_status_and_uninstall(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(windows.subprocess, "run", lambda arguments, **kwargs: SimpleNamespace(returncode=0, stdout="Status: Running"))

    marker = windows.install("C:/venv/ai-usage.exe", ["up"], tmp_path)
    status = windows.status(tmp_path)
    windows.uninstall(tmp_path)

    assert status.installed and status.active and status.mode == "both"
    assert not marker.exists()
# end def
