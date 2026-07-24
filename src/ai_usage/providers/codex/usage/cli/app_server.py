"""Codex app-server usage method: JSON-RPC over stdio subprocess."""

import asyncio
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_usage.models import AccountConfig, AccountIdentity, ProviderFetchResult
from ai_usage.providers.base import CredentialKind, ProviderError, UsageMethod
from ai_usage.providers.codex.usage.web.private_api import codex_app_server_email, parse_rate_limits


class AppServerClient:
    def __init__(self, command: str, environment: dict[str, str]):
        self.command = command
        self.environment = environment
        self.process: asyncio.subprocess.Process | None = None
        self.request_id = 0
    # end def

    async def __aenter__(self) -> "AppServerClient":
        self.process = await asyncio.create_subprocess_exec(
            self.command,
            "app-server",
            "--stdio",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self.environment,
        )
        await self.request(
            "initialize",
            {"clientInfo": {"name": "ai-usage", "title": "AI Usage", "version": "0.1.0"}},
        )
        await self.notify("initialized", {})
        return self
    # end def

    async def __aexit__(self, exception_type: Any, exception: Any, traceback: Any) -> None:
        del exception_type, exception, traceback
        if self.process is not None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=3)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
            # end try
        # end if
    # end def

    async def send(self, payload: dict[str, Any]) -> None:
        if self.process is None or self.process.stdin is None:
            raise ProviderError("Codex app-server is not running")
        # end if
        self.process.stdin.write(json.dumps(payload, separators=(",", ":")).encode() + b"\n")
        await self.process.stdin.drain()
    # end def

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        await self.send({"method": method, "params": params})
    # end def

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.process is None or self.process.stdout is None:
            raise ProviderError("Codex app-server is not running")
        # end if
        self.request_id += 1
        request_id = self.request_id
        payload: dict[str, Any] = {"method": method, "id": request_id}
        if params is not None:
            payload["params"] = params
        # end if
        await self.send(payload)
        while line := await asyncio.wait_for(self.process.stdout.readline(), timeout=30):
            message = json.loads(line)
            if message.get("id") != request_id:
                continue
            # end if
            if "error" in message:
                raise ProviderError(f"Codex {method} failed: {message['error']}")
            # end if
            result: dict[str, Any] = message.get("result") or {}
            return result
        # end while
        raise ProviderError(f"Codex app-server closed while waiting for {method}")
    # end def
# end class


class AppServerUsage(UsageMethod):
    """Fetches Codex usage by driving `codex app-server` over stdio JSON-RPC."""

    required_credential_kind: CredentialKind = "app_token"

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        environment = dict(os.environ)
        profile_dir = account.options.get("profile_dir")
        temporary: tempfile.TemporaryDirectory[str] | None = None
        # A manually-supplied credential carries the raw auth.json contents rather than a path on
        # disk (unlike the locally-discovered case, which already points `profile_dir` at the
        # real `~/.codex` directory). We materialize it as a temp file scoped to this single
        # fetch call -- its lifetime is tied to the app-server subprocess we're about to spawn, so
        # it is created and cleaned up here rather than during login.
        if credential and credential.get("auth_json"):
            temporary = tempfile.TemporaryDirectory(prefix="ai-usage-codex-")
            auth_file = Path(temporary.name) / "auth.json"
            auth_file.write_text(json.dumps(credential["auth_json"]), encoding="utf-8")
            auth_file.chmod(0o600)
            profile_dir = temporary.name
        # end if
        if profile_dir:
            environment["CODEX_HOME"] = str(Path(profile_dir).expanduser())
        # end if
        observed = datetime.now(UTC)
        try:
            async with AppServerClient(
                str(account.options.get("command", "codex")), environment
            ) as client:
                account_result = await client.request("account/read", {"refreshToken": True})
                result = await client.request("account/rateLimits/read")
            # end with
        except FileNotFoundError as exception:
            raise ProviderError("Codex CLI was not found") from exception
        finally:
            if temporary is not None:
                temporary.cleanup()
            # end if
        # end try
        return ProviderFetchResult(
            service="codex",
            provider="app-server",
            account_id=account.id,
            fetched_at=observed,
            metrics=parse_rate_limits(result, observed),
            identity=AccountIdentity(email=codex_app_server_email(account_result)),
        )
    # end def
# end class
