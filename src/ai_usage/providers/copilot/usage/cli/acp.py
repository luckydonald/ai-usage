"""Collect Copilot account Plan usage through its ACP stdio endpoint."""

import asyncio
import json
import os
import re
from datetime import UTC, datetime
from typing import Any

from ai_usage.models import AccountConfig, AccountIdentity, Metric, MinMaxUsage, ProviderFetchResult
from ai_usage.providers.base import ProviderError, UsageMethod

ACP_REQUEST_TIMEOUT_SECONDS = 20
ACP_PROCESS_TIMEOUT_SECONDS = 3
COPILOT_ACP_ARGS = (
    "--acp",
    "--stdio",
    "--reasoning-effort=none",
    "--available-tools=",
    "--disable-builtin-mcps",
    "--disallow-temp-dir",
    "--no-ask-user",
    "--no-auto-update",
    "--no-bash-env",
    "--no-custom-instructions",
    "--no-experimental",
    "--no-remote",
    "--no-remote-export",
)
PLAN_AMOUNT_PATTERN = re.compile(
    r"(?P<current>[\d,]+)\s*/\s*(?P<maximum>[\d,]+)\s*AIC\b", re.IGNORECASE
)
PLAN_SECTION_END_PATTERN = re.compile(
    r"(?im)^\s*(?:Session|Current\s+session|Premium\s+requests?|Models?)\s*$"
)
GITHUB_USER_PATTERN = re.compile(
    r"(?:GitHub\s+(?:user(?:name)?|login)|(?:logged\s+in\s+as|username))\s*:\s*"
    r"(?P<login>[A-Za-z0-9-]+)",
    re.IGNORECASE,
)


class CopilotAcpClient:
    """Small JSON-RPC ACP client scoped to one short-lived Copilot process."""

    def __init__(self, command: str) -> None:
        self.command = command
        self.process: asyncio.subprocess.Process | None = None
        self.request_id = 0
    # end def

    async def __aenter__(self) -> "CopilotAcpClient":
        try:
            self.process = await asyncio.create_subprocess_exec(
                self.command,
                *COPILOT_ACP_ARGS,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exception:
            raise ProviderError("Copilot CLI was not found or could not start") from exception
        # end try
        try:
            await self.request(
                "initialize",
                {
                    "protocolVersion": 1,
                    "clientCapabilities": {},
                    "clientInfo": {"name": "ai-usage", "version": "0.1.0"},
                },
            )
        except BaseException:
            await self.close()
            raise
        # end try
        return self
    # end def

    async def __aexit__(self, exception_type: Any, exception: Any, traceback: Any) -> None:
        del exception_type, exception, traceback
        await self.close()
    # end def

    async def close(self) -> None:
        if self.process is None or self.process.returncode is not None:
            return
        # end if
        self.process.terminate()
        try:
            await asyncio.wait_for(self.process.wait(), timeout=ACP_PROCESS_TIMEOUT_SECONDS)
        except TimeoutError:
            self.process.kill()
            await self.process.wait()
        # end try
    # end def

    async def send(self, message: dict[str, Any]) -> None:
        if self.process is None or self.process.stdin is None:
            raise ProviderError("Copilot ACP process is not running")
        # end if
        self.process.stdin.write(json.dumps(message, separators=(",", ":")).encode() + b"\n")
        await self.process.stdin.drain()
    # end def

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.request_id += 1
        request_id = self.request_id
        await self.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        return await self.response_for(request_id, method)
    # end def

    async def response_for(self, request_id: int, method: str) -> dict[str, Any]:
        while True:
            message = await self.read_message(method)
            if "method" in message and "id" in message:
                await self.reject_agent_request(message)
                raise ProviderError(f"Copilot ACP requested {message['method']}; requests are not allowed")
            # end if
            if message.get("id") != request_id:
                continue
            # end if
            if "error" in message:
                raise ProviderError(f"Copilot ACP {method} failed: {message['error']}")
            # end if
            result = message.get("result")
            if not isinstance(result, dict):
                raise ProviderError(f"Copilot ACP {method} returned an invalid response")
            # end if
            return result
        # end while
    # end def

    async def read_message(self, method: str) -> dict[str, Any]:
        if self.process is None or self.process.stdout is None:
            raise ProviderError("Copilot ACP process is not running")
        # end if
        try:
            line = await asyncio.wait_for(
                self.process.stdout.readline(), timeout=ACP_REQUEST_TIMEOUT_SECONDS
            )
        except TimeoutError as exception:
            raise ProviderError(f"Copilot ACP timed out while waiting for {method}") from exception
        # end try
        if not line:
            returncode = await self.process.wait()
            raise ProviderError(f"Copilot ACP closed while waiting for {method} (exit {returncode})")
        # end if
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exception:
            raise ProviderError("Copilot ACP returned invalid JSON") from exception
        # end try
        if not isinstance(message, dict):
            raise ProviderError("Copilot ACP returned an invalid JSON-RPC message")
        # end if
        return message
    # end def

    async def reject_agent_request(self, message: dict[str, Any]) -> None:
        await self.send(
            {
                "jsonrpc": "2.0",
                "id": message["id"],
                "error": {"code": -32000, "message": "ai-usage does not grant ACP permissions"},
            }
        )
    # end def

    async def open_session(self) -> str:
        result = await self.request("session/new", {"cwd": os.getcwd(), "mcpServers": []})
        session_id = result.get("sessionId")
        if not isinstance(session_id, str) or not session_id:
            raise ProviderError("Copilot ACP did not return a session ID")
        # end if
        return session_id
    # end def

    async def slash_command(self, session_id: str, command: str) -> str:
        self.request_id += 1
        request_id = self.request_id
        await self.send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "session/prompt",
                "params": {
                    "sessionId": session_id,
                    "prompt": [{"type": "text", "text": command}],
                },
            }
        )
        chunks: list[str] = []
        while True:
            message = await self.read_message("session/prompt")
            if "method" in message and "id" in message:
                await self.reject_agent_request(message)
                raise ProviderError(f"Copilot ACP requested {message['method']}; requests are not allowed")
            # end if
            if message.get("method") == "session/update":
                chunk = acp_text_chunk(message)
                if chunk is not None:
                    chunks.append(chunk)
                # end if
                continue
            # end if
            if message.get("id") != request_id:
                continue
            # end if
            if "error" in message:
                raise ProviderError(f"Copilot ACP session/prompt failed: {message['error']}")
            # end if
            if not isinstance(message.get("result"), dict):
                raise ProviderError("Copilot ACP session/prompt returned an invalid response")
            # end if
            return "".join(chunks)
        # end while
    # end def
# end class


def acp_text_chunk(message: dict[str, Any]) -> str | None:
    """Return an ACP agent-message text delta, ignoring all other notifications."""
    params = message.get("params")
    if not isinstance(params, dict):
        return None
    # end if
    update = params.get("update")
    if not isinstance(update, dict) or update.get("sessionUpdate") != "agent_message_chunk":
        return None
    # end if
    content = update.get("content")
    if not isinstance(content, dict) or content.get("type") != "text":
        return None
    # end if
    text = content.get("text")
    return text if isinstance(text, str) else None
# end def


def parse_plan_usage(output: str, observed_at: datetime) -> Metric:
    """Extract the account-level Plan AIC allowance, excluding session counters."""
    plan_match = re.search(r"(?im)^\s*Plan\s*$", output)
    if plan_match is None:
        raise ProviderError("Copilot /usage output did not contain a Plan allowance")
    # end if
    next_section = PLAN_SECTION_END_PATTERN.search(output, plan_match.end())
    plan_block_end = next_section.start() if next_section is not None else len(output)
    amount_match = PLAN_AMOUNT_PATTERN.search(output, plan_match.end(), plan_block_end)
    if amount_match is None:
        raise ProviderError("Copilot Plan allowance did not contain AIC amounts")
    # end if
    current = int(amount_match.group("current").replace(",", ""))
    maximum = int(amount_match.group("maximum").replace(",", ""))
    if maximum <= 0 or current > maximum:
        raise ProviderError("Copilot Plan allowance contains invalid AIC amounts")
    # end if
    return Metric(
        key="plan",
        name="Plan",
        usage=MinMaxUsage(current=current, maximum=maximum, unit="AIC"),
        observed_at=observed_at,
    )
# end def


def parse_github_login(output: str) -> AccountIdentity:
    """Extract the active GitHub username reported by Copilot's `/user show` command."""
    match = GITHUB_USER_PATTERN.search(output)
    if match is None:
        raise ProviderError("Copilot /user show output did not contain a GitHub login")
    # end if
    return AccountIdentity(name=match.group("login"))
# end def


class CopilotAcpUsage(UsageMethod):
    """Fetch the Copilot account Plan allowance through a fresh restricted ACP session."""

    required_credential_kind = "none"

    async def fetch(
        self, account: AccountConfig, credential: dict[str, Any] | None
    ) -> ProviderFetchResult:
        del credential
        observed_at = datetime.now(UTC)
        command = str(account.options.get("command", "copilot"))
        async with CopilotAcpClient(command) as client:
            session_id = await client.open_session()
            usage_output = await client.slash_command(session_id, "/usage")
            user_output = await client.slash_command(session_id, "/user show")
        # end with
        return ProviderFetchResult(
            service=account.service,
            provider=account.provider,
            account_id=account.id,
            fetched_at=observed_at,
            metrics=[parse_plan_usage(usage_output, observed_at)],
            identity=parse_github_login(user_output),
        )
    # end def
# end class
