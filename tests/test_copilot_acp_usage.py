import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import pytest

from ai_usage.models import AccountConfig
from ai_usage.providers import built_in_registry
from ai_usage.providers.base import ProviderError
from ai_usage.providers.copilot.provider import CopilotCliUsageProvider
from ai_usage.providers.copilot.usage.cli.acp import (
    COPILOT_ACP_ARGS,
    CopilotAcpClient,
    CopilotAcpUsage,
    parse_github_login,
    parse_plan_usage,
)


class FakeStdin:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
    # end def

    def write(self, data: bytes) -> None:
        self.messages.append(json.loads(data))
    # end def

    async def drain(self) -> None:
        return None
    # end def
# end class


class FakeAcpProcess:
    def __init__(self, messages: list[dict[str, Any]], returncode: int | None = None) -> None:
        self.stdin = FakeStdin()
        self.stdout = asyncio.StreamReader()
        self.stderr = asyncio.StreamReader()
        self.returncode = returncode
        self.terminated = False
        self.killed = False
        for message in messages:
            self.stdout.feed_data(json.dumps(message).encode() + b"\n")
        # end for
        self.stdout.feed_eof()
    # end def

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0
    # end def

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9
    # end def

    async def wait(self) -> int:
        return self.returncode if self.returncode is not None else 0
    # end def
# end class


def response(request_id: int, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}
# end def


def text_update(text: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {
            "sessionId": "session-1",
            "update": {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": text},
            },
        },
    }
# end def


def test_parse_plan_usage_handles_commas_and_whitespace() -> None:
    metric = parse_plan_usage(
        "\n Plan \n  88% used\n  4,425 / 5,000   AIC\n", datetime.now(UTC)
    )
    assert metric.key == "plan"
    assert metric.usage.current == 4425
    assert metric.usage.maximum == 5000
    assert metric.usage.unit == "AIC"
# end def


@pytest.mark.parametrize(
    "output",
    [
        "4,425 / 5,000 AIC",
        "Plan\n88% used",
        "Plan\n4,425 / zero AIC",
        "Plan\n88% used\nSession\n4,425 / 5,000 AIC",
    ],
)
def test_parse_plan_usage_rejects_missing_or_invalid_plan(output: str) -> None:
    with pytest.raises(ProviderError, match="Plan"):
        parse_plan_usage(output, datetime.now(UTC))
    # end with
# end def


def test_parse_github_login_uses_reported_github_user() -> None:
    assert parse_github_login("GitHub user: octo-cat").name == "octo-cat"
# end def


@pytest.mark.asyncio
async def test_acp_collects_ordered_chunks_and_ignores_notifications(monkeypatch) -> None:
    process = FakeAcpProcess(
        [
            response(1, {"protocolVersion": 1}),
            response(2, {"sessionId": "session-1"}),
            {"jsonrpc": "2.0", "method": "session/notification", "params": {}},
            text_update("Plan\n"),
            text_update("4,425 / 5,000 AIC"),
            response(3, {"stopReason": "end_turn"}),
        ]
    )

    async def fake_create_subprocess_exec(*args: Any, **kwargs: Any) -> FakeAcpProcess:
        del args, kwargs
        return process
    # end def

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_create_subprocess_exec)
    async with CopilotAcpClient("copilot") as client:
        session_id = await client.open_session()
        output = await client.slash_command(session_id, "/usage")
    # end with

    assert output == "Plan\n4,425 / 5,000 AIC"
    assert [message.get("method") for message in process.stdin.messages] == [
        "initialize",
        "session/new",
        "session/prompt",
    ]
    assert process.stdin.messages[2]["params"]["prompt"][0]["text"] == "/usage"
    assert process.terminated
# end def


@pytest.mark.asyncio
async def test_acp_rejects_permission_requests_and_cleans_up(monkeypatch) -> None:
    permission_request = {
        "jsonrpc": "2.0",
        "id": 99,
        "method": "session/request_permission",
        "params": {},
    }
    process = FakeAcpProcess([response(1, {"protocolVersion": 1}), permission_request])

    async def fake_create_subprocess_exec(*args: Any, **kwargs: Any) -> FakeAcpProcess:
        del args, kwargs
        return process
    # end def

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_create_subprocess_exec)
    with pytest.raises(ProviderError, match="requests are not allowed"):
        async with CopilotAcpClient("copilot") as client:
            await client.open_session()
        # end with
    # end with
    assert process.stdin.messages[-1]["error"]["code"] == -32000
    assert process.terminated
# end def


@pytest.mark.asyncio
async def test_acp_reports_process_failures(monkeypatch) -> None:
    process = FakeAcpProcess([], returncode=7)

    async def fake_create_subprocess_exec(*args: Any, **kwargs: Any) -> FakeAcpProcess:
        del args, kwargs
        return process
    # end def

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_create_subprocess_exec)
    with pytest.raises(ProviderError, match="exit 7"):
        async with CopilotAcpClient("copilot"):
            pass
        # end with
    # end with
# end def


@pytest.mark.asyncio
async def test_acp_reports_request_timeouts(monkeypatch) -> None:
    process = FakeAcpProcess([])
    process.stdout = asyncio.StreamReader()

    async def fake_create_subprocess_exec(*args: Any, **kwargs: Any) -> FakeAcpProcess:
        del args, kwargs
        return process
    # end def

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr("ai_usage.providers.copilot.usage.cli.acp.ACP_REQUEST_TIMEOUT_SECONDS", 0)
    with pytest.raises(ProviderError, match="timed out"):
        async with CopilotAcpClient("copilot"):
            pass
        # end with
    # end with
    assert process.terminated
# end def


@pytest.mark.asyncio
async def test_cli_usage_provider_fetches_plan_and_identity(monkeypatch) -> None:
    process = FakeAcpProcess(
        [
            response(1, {"protocolVersion": 1}),
            response(2, {"sessionId": "session-1"}),
            text_update("Plan\n88% used\n4,425/5,000 AIC\n"),
            response(3, {"stopReason": "end_turn"}),
            text_update("GitHub username: octocat"),
            response(4, {"stopReason": "end_turn"}),
        ]
    )

    async def fake_create_subprocess_exec(*args: Any, **kwargs: Any) -> FakeAcpProcess:
        del args, kwargs
        return process
    # end def

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_create_subprocess_exec)
    account = AccountConfig(id="copilot", service="copilot", provider="cli-usage", name="Copilot")
    result = await CopilotAcpUsage().fetch(account, None)

    assert result.metrics[0].key == "plan"
    assert result.metrics[0].usage.current == 4425
    assert result.identity is not None
    assert result.identity.name == "octocat"
    assert CopilotCliUsageProvider().user_identity(account, result) == "octocat"
# end def


def test_cli_usage_provider_is_registered_with_restricted_arguments() -> None:
    provider = built_in_registry().get("copilot", "cli-usage")
    assert isinstance(provider, CopilotCliUsageProvider)
    assert provider.required_credential_kind == "none"
    assert provider.login_methods == ()
    assert "--acp" in COPILOT_ACP_ARGS
    assert "--interactive" not in COPILOT_ACP_ARGS
    assert "--max-ai-credits" not in COPILOT_ACP_ARGS
# end def
