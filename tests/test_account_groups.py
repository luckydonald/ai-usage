from ai_usage.account_groups import account_group_ids
from ai_usage.models import AccountConfig


def test_same_service_login_gets_one_derived_group() -> None:
    first = AccountConfig(
        id="config-one",
        service="claude",
        provider="web",
        name="legacy",
        login="user@example.com|org-1",
    )
    second = first.model_copy(update={"id": "config-two", "provider": "cli-usage"})

    groups = account_group_ids([first, second])

    assert groups["config-one"] == groups["config-two"]
# end def


def test_different_services_or_unresolved_logins_do_not_group() -> None:
    first = AccountConfig(
        id="config-one",
        service="claude",
        provider="web",
        name="legacy",
        login="user@example.com|org-1",
    )
    other_service = first.model_copy(update={"id": "config-two", "service": "codex"})
    unresolved = first.model_copy(update={"id": "config-three", "login": None})

    assert account_group_ids([first, other_service, unresolved]) == {}
# end def
