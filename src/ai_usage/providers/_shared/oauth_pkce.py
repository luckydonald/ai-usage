"""Generic OAuth 2.0 Authorization Code + PKCE login, with a local loopback callback server.

No provider in this codebase used PKCE before SuperGrok (xAI) — Claude/Codex use browser
cookie-jar capture instead. This helper is intentionally provider-agnostic: only
`run_pkce_login`'s keyword arguments carry vendor specifics (client id, endpoints, scopes).
"""

import asyncio
import base64
import hashlib
import http.server
import queue
import secrets
import threading
import urllib.parse
import webbrowser
from dataclasses import dataclass
from typing import Any

import httpx

from ai_usage.providers.base import ProviderError

DEFAULT_CALLBACK_TIMEOUT_SECONDS = 300.0


@dataclass(frozen=True)
class PkceExchange:
    access_token: str
    refresh_token: str | None
    id_token: str | None
    expires_in: int | None
    raw: dict[str, Any]
# end class


def _generate_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge
# end def


def _run_callback_server(host: str, port: int, result_queue: queue.Queue) -> http.server.HTTPServer:
    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            del format, args
        # end def

        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlsplit(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            body = b"<html><body>Login complete, you can close this tab.</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True
            result_queue.put(
                {
                    "code": (params.get("code") or [None])[0],
                    "state": (params.get("state") or [None])[0],
                    "error": (params.get("error") or [None])[0],
                }
            )
        # end def
    # end class

    try:
        server = http.server.HTTPServer((host, port), CallbackHandler)
    except OSError as exception:
        raise ProviderError(
            f"could not start OAuth callback listener on {host}:{port} — is another login "
            f"attempt already running? ({exception})"
        ) from exception
    # end try
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
# end def


async def run_pkce_login(
    *,
    authorization_endpoint: str,
    token_endpoint: str,
    client_id: str,
    redirect_uri: str,
    scopes: list[str] | tuple[str, ...],
    extra_authorize_params: dict[str, str] | None = None,
    include_nonce: bool = False,
    callback_timeout: float = DEFAULT_CALLBACK_TIMEOUT_SECONDS,
) -> PkceExchange:
    """Run a full PKCE authorization-code login, blocking (async-friendly) until it completes.

    `redirect_uri` must be an `http://127.0.0.1:<port>/<path>`-shaped loopback URL matching a
    registered redirect for the vendor's OAuth client — the port is fixed by the vendor, not
    chosen by this helper.
    """
    parsed_redirect = urllib.parse.urlsplit(redirect_uri)
    host = parsed_redirect.hostname or "127.0.0.1"
    port = parsed_redirect.port
    if port is None:
        raise ProviderError(f"redirect_uri {redirect_uri!r} must include an explicit port")
    # end if

    verifier, challenge = _generate_pkce_pair()
    state = secrets.token_urlsafe(16)

    authorize_params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if include_nonce:
        authorize_params["nonce"] = secrets.token_urlsafe(16)
    # end if
    if extra_authorize_params:
        authorize_params.update(extra_authorize_params)
    # end if
    authorize_url = f"{authorization_endpoint}?{urllib.parse.urlencode(authorize_params)}"

    result_queue: queue.Queue = queue.Queue()
    server = _run_callback_server(host, port, result_queue)
    try:
        webbrowser.open(authorize_url)
        try:
            callback = await _wait_for_callback(result_queue, callback_timeout)
        except (queue.Empty, TimeoutError) as exception:
            raise ProviderError("timed out waiting for the OAuth login callback") from exception
        # end try
    finally:
        server.shutdown()
        server.server_close()
    # end try

    if callback.get("error"):
        raise ProviderError(f"OAuth login was denied or failed: {callback['error']}")
    # end if
    if callback.get("state") != state:
        raise ProviderError("OAuth callback state did not match — possible CSRF, aborting login")
    # end if
    code = callback.get("code")
    if not code:
        raise ProviderError("OAuth callback did not include an authorization code")
    # end if

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "code_verifier": verifier,
            },
        )
    # end async with
    if response.status_code != 200:
        raise ProviderError(f"OAuth token exchange failed: HTTP {response.status_code}")
    # end if
    payload: dict[str, Any] = response.json()
    access_token = payload.get("access_token")
    if not access_token:
        raise ProviderError("OAuth token response did not include an access_token")
    # end if
    return PkceExchange(
        access_token=access_token,
        refresh_token=payload.get("refresh_token"),
        id_token=payload.get("id_token"),
        expires_in=payload.get("expires_in"),
        raw=payload,
    )
# end def


async def _wait_for_callback(result_queue: queue.Queue, wait_seconds: float) -> dict[str, Any]:
    return await asyncio.wait_for(
        asyncio.to_thread(result_queue.get, True, wait_seconds), wait_seconds + 5
    )
# end def
