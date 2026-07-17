import pytest

from ai_usage.sentry import init_sentry, sample_rate


def test_sentry_is_inert_without_dsn(monkeypatch) -> None:
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    init_sentry()
# end def


def test_trace_sample_rate_validation() -> None:
    assert sample_rate(None) == 0
    assert sample_rate("0.25") == 0.25
    with pytest.raises(ValueError):
        sample_rate("2")
    # end with
# end def
