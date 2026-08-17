import json
import os
import subprocess
import sys

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.memory import create_connected_server_and_client_session

from src.mcp_server import build_server
from src.settings import load_settings


@pytest.fixture
def settings(tmp_path):
    return load_settings(
        {
            "CAL_AUTO_CONFIG_DIR": str(tmp_path),
            "CAL_AUTO_TIMEZONE": "UTC",
            "GITHUB_TOKEN": "token",
            "GITHUB_PROJECT_ID": "project",
        }
    )


@pytest.mark.anyio
async def test_status_tool_is_listed_with_correct_schema(settings):
    async with create_connected_server_and_client_session(
        build_server(settings)._mcp_server
    ) as client:
        tools = await client.list_tools()

    names = [tool.name for tool in tools.tools]
    assert "status" in names

    status_tool = next(tool for tool in tools.tools if tool.name == "status")
    schema_properties = status_tool.outputSchema["properties"]
    assert set(schema_properties) == {
        "github_configured",
        "google_calendar_configured",
        "google_calendar_authorized",
    }
    for property_schema in schema_properties.values():
        assert property_schema["type"] == "boolean"


@pytest.mark.anyio
async def test_status_tool_reports_configuration_without_secrets(settings):
    async with create_connected_server_and_client_session(
        build_server(settings)._mcp_server
    ) as client:
        result = await client.call_tool("status", {})

    assert result.structuredContent == {
        "github_configured": True,
        "google_calendar_configured": False,
        "google_calendar_authorized": False,
    }
    payload = json.dumps(result.structuredContent)
    assert "token" not in payload


def _write_token(settings, **fields):
    token = {
        "client_id": "client",
        "client_secret": "secret",
        "refresh_token": None,
        "token": "access-token",
        "scopes": ["https://www.googleapis.com/auth/calendar"],
        "expiry": "2099-01-01T00:00:00Z",
    }
    token.update(fields)
    settings.google_token_file.write_text(json.dumps(token))


@pytest.mark.anyio
async def test_status_tool_reports_authorized_for_a_valid_unexpired_token(settings):
    _write_token(settings)

    async with create_connected_server_and_client_session(
        build_server(settings)._mcp_server
    ) as client:
        result = await client.call_tool("status", {})

    assert result.structuredContent["google_calendar_authorized"] is True


@pytest.mark.anyio
async def test_status_tool_reports_authorized_for_an_expired_but_refreshable_token(settings):
    _write_token(settings, expiry="2000-01-01T00:00:00Z", refresh_token="refresh")

    async with create_connected_server_and_client_session(
        build_server(settings)._mcp_server
    ) as client:
        result = await client.call_tool("status", {})

    assert result.structuredContent["google_calendar_authorized"] is True


@pytest.mark.anyio
async def test_status_tool_reports_unauthorized_for_an_expired_unrefreshable_token(settings):
    _write_token(settings, expiry="2000-01-01T00:00:00Z", refresh_token=None)

    async with create_connected_server_and_client_session(
        build_server(settings)._mcp_server
    ) as client:
        result = await client.call_tool("status", {})

    assert result.structuredContent["google_calendar_authorized"] is False


@pytest.mark.anyio
async def test_status_tool_reports_unauthorized_for_a_malformed_token_file(settings):
    settings.google_token_file.write_text("not json")

    async with create_connected_server_and_client_session(
        build_server(settings)._mcp_server
    ) as client:
        result = await client.call_tool("status", {})

    assert result.structuredContent["google_calendar_authorized"] is False


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _server_env(tmp_path):
    env = dict(os.environ)
    env["CAL_AUTO_CONFIG_DIR"] = str(tmp_path)
    env["CAL_AUTO_TIMEZONE"] = "UTC"
    return env


def test_only_protocol_traffic_appears_on_standard_output(tmp_path):
    process = subprocess.Popen(
        [sys.executable, "-m", "src.main", "server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_server_env(tmp_path),
        text=True,
    )
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "0.0.1"},
        },
    }
    try:
        process.stdin.write(json.dumps(request) + "\n")
        process.stdin.flush()
        line = process.stdout.readline()
    finally:
        process.terminate()
        process.wait(timeout=5)

    response = json.loads(line)
    assert response["id"] == 1
    assert "result" in response


def test_real_client_completes_initial_handshake(tmp_path):
    async def handshake():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "src.main", "server"],
            env=_server_env(tmp_path),
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                result = await session.initialize()
                return result.serverInfo.name

    import anyio

    server_name = anyio.run(handshake)
    assert server_name == "auto-calendar"
