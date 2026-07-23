"""Derived display groups for configurations that observe one real-world login."""

import uuid

from ai_usage.models import AccountConfig


def group_key(service: str, login: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"ai-usage/login/{service}/{login}"))
# end def


def account_group_ids(accounts: list[AccountConfig]) -> dict[str, str]:
    members: dict[tuple[str, str], list[AccountConfig]] = {}
    for account in accounts:
        if account.login:
            members.setdefault((account.service, account.login), []).append(account)
        # end if
    # end for
    groups: dict[str, str] = {}
    for (service, login), grouped_accounts in members.items():
        if len(grouped_accounts) > 1:
            key = group_key(service, login)
            groups.update({account.id: key for account in grouped_accounts})
        # end if
    # end for
    return groups
# end def
