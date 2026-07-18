import uuid

from ai_usage.settings import Paths


def test_credential_key_lives_under_local(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AI_USAGE_HOME", str(tmp_path))
    paths = Paths.from_environment()

    assert paths.credential_key == paths.local / "credential.key"
# end def


def test_ensure_migrates_legacy_credential_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AI_USAGE_HOME", str(tmp_path))
    tmp_path.mkdir(parents=True, exist_ok=True)
    legacy = tmp_path / "credential.key"
    legacy.write_text("legacy-secret", encoding="utf-8")

    paths = Paths.from_environment()
    paths.ensure()

    assert not legacy.exists()
    assert paths.credential_key.read_text(encoding="utf-8") == "legacy-secret"
    assert "/credential.key" not in (paths.root / ".gitignore").read_text(encoding="utf-8")
# end def


def test_new_ids_are_uuid7() -> None:
    generated = uuid.uuid7()
    assert generated.version == 7
# end def
