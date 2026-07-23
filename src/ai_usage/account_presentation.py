"""Provider-aware account hierarchy data for the dashboard."""

from dataclasses import dataclass

from ai_usage.models import AccountConfig


@dataclass(frozen=True)
class OrganizationPresentation:
    id: str
    name: str | None
# end class


@dataclass(frozen=True)
class AccountPresentation:
    login: str | None
    organization: OrganizationPresentation | None = None
# end class


def normalized_organization_name(login: str, name: str | None) -> str | None:
    if name is None:
        return None
    # end if
    generic = f"{login}'s Organization"
    return None if name.casefold() == generic.casefold() else name
# end def


def account_presentation(account: AccountConfig) -> AccountPresentation:
    login = account.login
    if account.service == "claude" and account.provider == "web" and login:
        primary_login, separator, organization_id = login.partition("|")
        if separator and organization_id:
            return AccountPresentation(
                login=primary_login,
                organization=OrganizationPresentation(
                    id=organization_id,
                    name=normalized_organization_name(primary_login, account.identity.name if account.identity else None),
                ),
            )
        # end if
    # end if
    return AccountPresentation(login=login)
# end def


def configuration_key(account: AccountConfig) -> tuple[str, str | None, str | None, str]:
    presentation = account_presentation(account)
    organization_id = presentation.organization.id if presentation.organization else None
    return account.service, presentation.login, organization_id, account.provider
# end def


def duplicate_configuration_ids(accounts: list[AccountConfig]) -> set[str]:
    by_key: dict[tuple[str, str | None, str | None, str], list[AccountConfig]] = {}
    for account in accounts:
        if account.login is not None:
            by_key.setdefault(configuration_key(account), []).append(account)
        # end if
    # end for
    return {account.id for grouped in by_key.values() if len(grouped) > 1 for account in grouped}
# end def
