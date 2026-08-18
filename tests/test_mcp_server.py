import json
import os
import subprocess
import sys
from datetime import datetime, timezone

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.memory import create_connected_server_and_client_session

from src.dtos.calendar_entry import CalendarEntryDTO, TodoItemDTO
from src.dtos.work_item import Priority, Size, WorkItem
from src.errors import AuthorizationError
from src.mcp_server import build_server
from src.providers.calendar_sink import CalendarSink
from src.providers.task_source import TaskSource
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


class StubTaskSource(TaskSource):
    def __init__(self, items):
        self.items = items

    def list_work_items(self, statuses=None):
        if statuses is None:
            return self.items
        wanted = set(statuses)
        return [item for item in self.items if item.status in wanted]


class StubCalendarSink(CalendarSink):
    def __init__(self, entries=None, todos=None):
        self.entries = entries or []
        self.todos = todos or []

    def list_busy_blocks(self, window):
        return []

    def list_entries(self, window):
        return self.entries

    def list_outstanding_todos(self):
        return self.todos

    def create_event(self, event):
        raise NotImplementedError

    def create_todo(self, task):
        raise NotImplementedError

    def has_scheduled_event(self, source, source_id, start):
        raise NotImplementedError

    def list_scheduled_todo_markers(self):
        raise NotImplementedError


class FailingTaskSource(TaskSource):
    def list_work_items(self, statuses=None):
        raise AuthorizationError(
            "GitHub token is invalid",
            hint="Run cal-auto-python authorize before starting the server.",
        )


class FailingCalendarSink(CalendarSink):
    def list_busy_blocks(self, window):
        raise NotImplementedError

    def list_entries(self, window):
        raise AuthorizationError(
            "Google account has not been authorised",
            hint="Run cal-auto-python authorize before starting the server.",
        )

    def list_outstanding_todos(self):
        raise AuthorizationError(
            "Google account has not been authorised",
            hint="Run cal-auto-python authorize before starting the server.",
        )

    def create_event(self, event):
        raise NotImplementedError

    def create_todo(self, task):
        raise NotImplementedError

    def has_scheduled_event(self, source, source_id, start):
        raise NotImplementedError

    def list_scheduled_todo_markers(self):
        raise NotImplementedError


@pytest.mark.anyio
async def test_list_calendar_entries_returns_structured_entries(settings):
    calendar_sink = StubCalendarSink(
        entries=[
            CalendarEntryDTO(
                title="Standup",
                start=datetime(2026, 8, 17, 9, tzinfo=timezone.utc),
                end=datetime(2026, 8, 17, 9, 30, tzinfo=timezone.utc),
                all_day=False,
            )
        ]
    )
    server = build_server(settings, calendar_sink_factory=lambda _settings: calendar_sink)

    async with create_connected_server_and_client_session(server._mcp_server) as client:
        tool = next(
            t for t in (await client.list_tools()).tools if t.name == "list_calendar_entries"
        )
        assert tool.annotations.readOnlyHint is True

        result = await client.call_tool(
            "list_calendar_entries", {"start": "2026-08-17", "end": "2026-08-17"}
        )

    assert result.structuredContent["entries"] == [
        {
            "title": "Standup",
            "start": "2026-08-17T09:00:00Z",
            "end": "2026-08-17T09:30:00Z",
            "all_day": False,
        }
    ]


@pytest.mark.anyio
async def test_list_todos_returns_structured_todos(settings):
    calendar_sink = StubCalendarSink(
        todos=[TodoItemDTO(title="Write report", status="needsAction", notes="due soon")]
    )
    server = build_server(settings, calendar_sink_factory=lambda _settings: calendar_sink)

    async with create_connected_server_and_client_session(server._mcp_server) as client:
        tool = next(t for t in (await client.list_tools()).tools if t.name == "list_todos")
        assert tool.annotations.readOnlyHint is True

        result = await client.call_tool("list_todos", {})

    assert result.structuredContent["todos"] == [
        {"title": "Write report", "status": "needsAction", "notes": "due soon", "due": None}
    ]


@pytest.mark.anyio
async def test_list_tracker_items_filters_by_status(settings):
    task_source = StubTaskSource(
        [
            WorkItem(id="1", title="Ship it", status="Backlog", priority=Priority.P1, size=Size.S),
            WorkItem(id="2", title="Done thing", status="Done"),
        ]
    )
    server = build_server(settings, task_source_factory=lambda _settings: task_source)

    async with create_connected_server_and_client_session(server._mcp_server) as client:
        tool = next(t for t in (await client.list_tools()).tools if t.name == "list_tracker_items")
        assert tool.annotations.readOnlyHint is True

        result = await client.call_tool("list_tracker_items", {"statuses": ["Backlog"]})

    assert [item["title"] for item in result.structuredContent["items"]] == ["Ship it"]
    assert result.structuredContent["items"][0]["priority"] == "P1"


@pytest.mark.anyio
async def test_list_tracker_items_returns_everything_without_a_status_filter(settings):
    task_source = StubTaskSource(
        [
            WorkItem(id="1", title="Ship it", status="Backlog"),
            WorkItem(id="2", title="Done thing", status="Done"),
        ]
    )
    server = build_server(settings, task_source_factory=lambda _settings: task_source)

    async with create_connected_server_and_client_session(server._mcp_server) as client:
        result = await client.call_tool("list_tracker_items", {})

    assert [item["title"] for item in result.structuredContent["items"]] == [
        "Ship it",
        "Done thing",
    ]


@pytest.mark.anyio
async def test_list_calendar_entries_surfaces_the_authorization_hint_when_unauthorized(settings):
    server = build_server(settings, calendar_sink_factory=lambda _settings: FailingCalendarSink())

    async with create_connected_server_and_client_session(server._mcp_server) as client:
        result = await client.call_tool(
            "list_calendar_entries", {"start": "2026-08-17", "end": "2026-08-17"}
        )

    assert result.isError is True
    message = result.content[0].text
    assert "Google account has not been authorised" in message
    assert "cal-auto-python authorize" in message


@pytest.mark.anyio
async def test_list_tracker_items_surfaces_the_authorization_hint_when_unauthorized(settings):
    server = build_server(settings, task_source_factory=lambda _settings: FailingTaskSource())

    async with create_connected_server_and_client_session(server._mcp_server) as client:
        result = await client.call_tool("list_tracker_items", {})

    assert result.isError is True
    message = result.content[0].text
    assert "GitHub token is invalid" in message
    assert "cal-auto-python authorize" in message


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
