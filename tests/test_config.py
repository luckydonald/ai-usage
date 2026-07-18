from ai_usage.config import ConfigStore
from ai_usage.models import AccountConfig
from tests.test_storage import temporary_paths


def test_structured_global_config_defaults_when_missing(tmp_path) -> None:
    paths = temporary_paths(tmp_path)
    paths.ensure()
    config = ConfigStore(paths)

    assert config.structured_global_config().git.enabled is False
# end def


def test_structured_global_config_falls_back_on_schema_mismatch(tmp_path) -> None:
    paths = temporary_paths(tmp_path)
    paths.ensure()
    (paths.root / "config.yml").write_text("git: not-an-object\n", encoding="utf-8")
    config = ConfigStore(paths)

    assert config.structured_global_config().git.enabled is False
# end def


def test_save_global_config_round_trips_and_preserves_other_keys(tmp_path) -> None:
    paths = temporary_paths(tmp_path)
    paths.ensure()
    (paths.root / "config.yml").write_text("intervals:\n  normal_seconds: 500\n", encoding="utf-8")
    config = ConfigStore(paths)

    config.save_global_config({"git": {"enabled": True}})

    assert config.structured_global_config().git.enabled is True
    assert config.global_config()["intervals"]["normal_seconds"] == 500
# end def


def test_interval_precedence(tmp_path) -> None:
    paths = temporary_paths(tmp_path)
    paths.ensure()
    (paths.root / "config.yml").write_text(
        """
intervals:
  normal_seconds: 500
services:
  claude:
    intervals:
      normal_seconds: 400
providers:
  statusline:
    intervals:
      normal_seconds: 300
""",
        encoding="utf-8",
    )
    account = AccountConfig(
        id="id",
        service="claude",
        provider="statusline",
        name="Claude",
        intervals={"normal_seconds": 200},
    )
    intervals = ConfigStore(paths).intervals_for(account)
    assert intervals["normal_seconds"] == 200
    assert intervals["active_seconds"] == 60
# end def

