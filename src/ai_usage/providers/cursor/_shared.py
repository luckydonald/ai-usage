"""Shared Cursor helpers: session-cookie token extraction."""

import urllib.parse

COOKIE_NAME = "WorkosCursorSessionToken"
SEPARATOR = "::"


def extract_cursor_bearer_token(cookies: dict[str, str]) -> str | None:
    raw = cookies.get(COOKIE_NAME)
    if not raw:
        return None
    # end if
    decoded = urllib.parse.unquote(raw)
    if SEPARATOR in decoded:
        _, _, token = decoded.rpartition(SEPARATOR)
        return token.strip() or None
    # end if
    return decoded if decoded.startswith("eyJ") else None
# end def


def extract_cursor_user_id(cookies: dict[str, str]) -> str | None:
    raw = cookies.get(COOKIE_NAME)
    if not raw:
        return None
    # end if
    decoded = urllib.parse.unquote(raw)
    if SEPARATOR not in decoded:
        return None
    # end if
    user_id, _, _ = decoded.partition(SEPARATOR)
    return user_id.strip() or None
# end def
