from ai_usage.account_presentation import account_presentation, duplicate_configuration_ids
from ai_usage.models import AccountConfig, AccountIdentity


def test_claude_presentation_splits_login_and_hides_generic_organization_name() -> None:
    account = AccountConfig(
        id="config",
        service="claude",
        provider="web",
        name="Claude",
        login="user@example.com|org-1",
        identity=AccountIdentity(name="user@example.com's Organization"),
    )

    presentation = account_presentation(account)

    assert presentation.login == "user@example.com"
    assert presentation.organization is not None
    assert presentation.organization.id == "org-1"
    assert presentation.organization.name is None
# end def


def test_duplicate_configuration_ids_only_reports_same_parser_and_account_path() -> None:
    first = AccountConfig(
        id="one", service="claude", provider="web", name="Web", login="user@example.com|org-1"
    )
    duplicate = first.model_copy(update={"id": "two"})
    distinct = first.model_copy(update={"id": "three", "provider": "statusline"})

    assert duplicate_configuration_ids([first, duplicate, distinct]) == {"one", "two"}
# end def
