import json
import os
import socket
import subprocess
import sys
from datetime import datetime, timezone

import anyio
import httpx
import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.memory import create_connected_server_and_client_session

from src.dtos.calendar_entry import CalendarEntryDTO, TodoItemDTO
from src.dtos.event import EventDTO
from src.dtos.task import TaskDTO
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
        self.created_events = []
        self.created_todos = []

    def list_busy_blocks(self, window):
        return []

    def list_entries(self, window):
        return self.entries

    def list_outstanding_todos(self):
        return self.todos

    def create_event(self, event):
        self.created_events.append(event)
        return {"id": "event-1"}

    def create_todo(self, task):
        self.created_todos.append(task)
        return {"id": "todo-1"}

    def find_scheduled_events(self, source, source_id):
        raise NotImplementedError

    def update_event(self, event_id, event):
        raise NotImplementedError

    def list_scheduled_todo_markers(self):
        raise NotImplementedError


class SyncCalendarSink(StubCalendarSink):
    def __init__(self, existing=None):
        super().__init__()
        self.existing = existing or {}
        self.updated_events = []
        self._event_ids = 0

    def list_busy_blocks(self, window):
        return []

    def create_event(self, event):
        self._event_ids += 1
        event_id = f"event-{self._event_ids}"
        properties = (event.extendedProperties or {}).get("private", {})
        source = properties.get("source_system")
        source_id = properties.get("source_id")
        if source and source_id:
            self.existing.setdefault((source, source_id), []).append(
                {"id": event_id, "start": event.start, "end": event.end}
            )
        self.created_events.append(event)
        return {"id": event_id}

    def find_scheduled_events(self, source, source_id):
        return self.existing.get((source, source_id), [])

    def update_event(self, event_id, event):
        self.updated_events.append((event_id, event))
        return {"id": event_id}

    def list_scheduled_todo_markers(self):
        return set()


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

    def find_scheduled_events(self, source, source_id):
        raise NotImplementedError

    def update_event(self, event_id, event):
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
async def test_plan_week_works_without_integrations_or_credentials(tmp_path):
    settings = load_settings({"CAL_AUTO_CONFIG_DIR": str(tmp_path), "CAL_AUTO_TIMEZONE": "UTC"})
    server = build_server(settings)

    async with create_connected_server_and_client_session(server._mcp_server) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
        assert tools["plan_week"].annotations.readOnlyHint is True
        result = await client.call_tool(
            "plan_week",
            {
                "items": [{"title": "Write report", "priority": "P1", "estimate": 2}],
                "start_date": "2026-08-17",
                "end_date": "2026-08-17",
                "working_day_start": "09:00",
                "working_day_end": "12:00",
            },
        )

    assert result.structuredContent["scheduled"][0]["title"] == "Write report"
    assert not (tmp_path / "credentials.json").exists()


def test_build_server_reports_the_given_version_during_the_handshake(tmp_path):
    settings = load_settings({"CAL_AUTO_CONFIG_DIR": str(tmp_path), "CAL_AUTO_TIMEZONE": "UTC"})
    server = build_server(settings, version="1.2.3")

    assert server._mcp_server.create_initialization_options().server_version == "1.2.3"


@pytest.mark.anyio
async def test_sync_backlog_previews_without_writing(settings):
    item = WorkItem(
        id="1", source="github", title="Write report", priority=Priority.P1, status="Backlog"
    )
    source = StubTaskSource([item])
    sink = SyncCalendarSink()
    server = build_server(
        settings,
        task_source_factory=lambda _settings: source,
        calendar_sink_factory=lambda _settings: sink,
    )

    async with create_connected_server_and_client_session(server._mcp_server) as client:
        tool = next(t for t in (await client.list_tools()).tools if t.name == "sync_backlog")
        assert tool.annotations.readOnlyHint is False
        result = await client.call_tool(
            "sync_backlog", {"start_date": "2026-08-17", "end_date": "2026-08-17"}
        )

    assert result.structuredContent["preview"] is True
    assert len(result.structuredContent["planned"]) == 1
    assert result.structuredContent["created"] == []
    assert sink.created_events == []
    assert sink.created_todos == []


@pytest.mark.anyio
async def test_sync_backlog_applies_and_reports_existing_items(settings):
    item = WorkItem(
        id="1", source="github", title="Write report", priority=Priority.P1, status="Backlog"
    )
    source = StubTaskSource([item])
    sink = SyncCalendarSink()
    server = build_server(
        settings,
        task_source_factory=lambda _settings: source,
        calendar_sink_factory=lambda _settings: sink,
    )

    async with create_connected_server_and_client_session(server._mcp_server) as client:
        first = await client.call_tool(
            "sync_backlog",
            {"start_date": "2026-08-17", "end_date": "2026-08-17", "apply": True},
        )
        second = await client.call_tool(
            "sync_backlog",
            {"start_date": "2026-08-17", "end_date": "2026-08-17", "apply": True},
        )

    assert len(first.structuredContent["created"]) == 1
    assert len(second.structuredContent["skipped"]) == 1
    assert len(sink.created_events) == 1


@pytest.mark.anyio
async def test_plan_week_does_not_use_network_when_network_fails(settings, monkeypatch):
    def fail_network(*args, **kwargs):
        raise AssertionError("plan_week attempted a network call")

    monkeypatch.setattr("requests.request", fail_network)
    server = build_server(settings)

    async with create_connected_server_and_client_session(server._mcp_server) as client:
        result = await client.call_tool(
            "plan_week",
            {
                "items": [{"title": "Small task", "estimate": 1}],
                "start_date": "2026-08-17",
                "end_date": "2026-08-17",
                "working_day_start": "09:00",
                "working_day_end": "09:30",
            },
        )

    assert result.structuredContent["unscheduled"] == [
        {"title": "Small task", "reason": "No available time remains in the scheduling window"}
    ]


@pytest.mark.anyio
async def test_plan_week_normalizes_and_validates_commitments(settings):
    server = build_server(settings)

    async with create_connected_server_and_client_session(server._mcp_server) as client:
        result = await client.call_tool(
            "plan_week",
            {
                "items": [{"title": "Focus work", "estimate": 1}],
                "start_date": "2026-08-17",
                "end_date": "2026-08-17",
                "working_day_start": "09:00",
                "working_day_end": "12:00",
                "timezone": "Europe/Lisbon",
                "commitments": [
                    {
                        "title": "Meeting",
                        "start": "2026-08-17T09:00:00",
                        "end": "2026-08-17T10:00:00",
                    }
                ],
            },
        )

    assert result.structuredContent["scheduled"][0]["start"] == "2026-08-17T10:00:00+01:00"


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
async def test_create_tools_write_one_entry_and_one_todo(settings):
    calendar_sink = StubCalendarSink()
    server = build_server(settings, calendar_sink_factory=lambda _settings: calendar_sink)

    async with create_connected_server_and_client_session(server._mcp_server) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
        assert tools["create_calendar_entry"].annotations.readOnlyHint is False
        assert tools["create_calendar_entry"].annotations.idempotentHint is False
        assert tools["create_calendar_entry"].annotations.openWorldHint is True
        event_result = await client.call_tool(
            "create_calendar_entry",
            {
                "summary": "Focus",
                "start": "2026-08-18T09:00:00",
                "end": "2026-08-18T10:00:00",
                "timezone": "Europe/Lisbon",
                "description": "Deep work",
                "attendees": ["person@example.com"],
            },
        )
        result = await client.call_tool(
            "create_todo", {"title": "Send notes", "note": "Before lunch", "due": "2026-08-18"}
        )

    assert len(calendar_sink.created_events) == 1
    assert isinstance(calendar_sink.created_events[0], EventDTO)
    assert calendar_sink.created_events[0].summary == "Focus"
    assert json.loads(event_result.content[0].text) == {"id": "event-1"}
    assert len(calendar_sink.created_todos) == 1
    assert isinstance(calendar_sink.created_todos[0], TaskDTO)
    assert calendar_sink.created_todos[0].due == "2026-08-18T00:00:00Z"
    assert json.loads(result.content[0].text) == {"id": "todo-1"}


@pytest.mark.anyio
async def test_create_calendar_entry_rejects_unknown_timezone_before_upstream(settings):
    calendar_sink = StubCalendarSink()
    server = build_server(settings, calendar_sink_factory=lambda _settings: calendar_sink)

    async with create_connected_server_and_client_session(server._mcp_server) as client:
        result = await client.call_tool(
            "create_calendar_entry",
            {
                "summary": "Invalid",
                "start": "2026-08-18T09:00:00",
                "end": "2026-08-18T10:00:00",
                "timezone": "Not/AZone",
            },
        )

    assert result.isError is True
    assert "Unknown timezone" in result.content[0].text
    assert calendar_sink.created_events == []


@pytest.mark.anyio
async def test_create_calendar_entry_rejects_end_before_start(settings):
    calendar_sink = StubCalendarSink()
    server = build_server(settings, calendar_sink_factory=lambda _settings: calendar_sink)

    async with create_connected_server_and_client_session(server._mcp_server) as client:
        result = await client.call_tool(
            "create_calendar_entry",
            {
                "summary": "Invalid",
                "start": "2026-08-18T10:00:00",
                "end": "2026-08-18T09:00:00",
                "timezone": "Europe/Lisbon",
            },
        )

    assert result.isError is True
    assert "end must be after" in result.content[0].text
    assert calendar_sink.created_events == []


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
async def test_list_calendar_entries_rejects_an_end_date_before_the_start_date(settings):
    server = build_server(settings, calendar_sink_factory=lambda _settings: StubCalendarSink())

    async with create_connected_server_and_client_session(server._mcp_server) as client:
        result = await client.call_tool(
            "list_calendar_entries", {"start": "2026-08-17", "end": "2026-08-16"}
        )

    assert result.isError is True
    assert "end date" in result.content[0].text


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


@pytest.mark.anyio
async def test_capabilities_behave_identically_over_http_transport(settings):
    item = WorkItem(
        id="1", source="github", title="Write report", priority=Priority.P1, status="Backlog"
    )
    source = StubTaskSource([item])
    sink = SyncCalendarSink()
    server = build_server(
        settings,
        task_source_factory=lambda _settings: source,
        calendar_sink_factory=lambda _settings: sink,
    )
    app = server.streamable_http_app()
    http_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app))

    async with server.session_manager.run():
        async with streamable_http_client("http://127.0.0.1:8000/mcp", http_client=http_client) as (
            read,
            write,
            _get_session_id,
        ):
            async with ClientSession(read, write) as client:
                await client.initialize()

                tools = {tool.name for tool in (await client.list_tools()).tools}
                assert "sync_backlog" in tools

                result = await client.call_tool(
                    "sync_backlog", {"start_date": "2026-08-17", "end_date": "2026-08-17"}
                )

    assert result.structuredContent["preview"] is True
    assert len(result.structuredContent["planned"]) == 1
    assert sink.created_events == []


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


def test_cli_serves_http_transport_and_completes_handshake(tmp_path):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "src.main",
            "server",
            "--transport",
            "http",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_server_env(tmp_path),
        text=True,
    )

    async def handshake():
        url = f"http://127.0.0.1:{port}/mcp"
        for _ in range(50):
            try:
                async with streamable_http_client(url) as (read, write, _get_session_id):
                    async with ClientSession(read, write) as session:
                        result = await session.initialize()
                        return result.serverInfo.name
            except Exception:
                await anyio.sleep(0.1)
        raise AssertionError("server never became reachable over HTTP")

    try:
        server_name = anyio.run(handshake)
    finally:
        process.terminate()
        process.wait(timeout=5)

    assert server_name == "auto-calendar"


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

    server_name = anyio.run(handshake)
    assert server_name == "auto-calendar"
