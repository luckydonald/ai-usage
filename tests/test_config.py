from ai_usage.config import ConfigStore
from ai_usage.models import AccountConfig
from tests.test_storage import temporary_paths


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

