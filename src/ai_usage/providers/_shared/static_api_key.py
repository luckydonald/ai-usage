"""Manual-paste static API key login, shared by providers with no OAuth/cookie flow."""

from collections.abc import Awaitable, Callable
from typing import Any

import click

from ai_usage.providers.base import LoginMethod, ProviderLoginError


class StaticApiKeyLogin(LoginMethod):
    """Prompts the user to paste a static API key/secret; no discovery, no refresh."""

    key = "paste-api-key"
    credential_kind = "bearer_token"

    def __init__(
        self,
        display_name: str,
        prompt_label: str = "API key",
        validate: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self.display_name = display_name
        self.prompt_label = prompt_label
        self._validate = validate
    # end def

    async def authenticate(self, options: dict[str, Any]) -> dict[str, Any] | None:
        del options
        key = click.prompt(self.prompt_label, hide_input=True).strip()
        if not key:
            raise ProviderLoginError(f"{self.display_name}: no API key entered")
        # end if
        if self._validate is not None:
            await self._validate(key)
        # end if
        return {"token": key}
    # end def
# end class
