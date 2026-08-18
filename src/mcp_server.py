"""MCP server exposing this tool's capabilities to an assistant."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Callable, List, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from google.oauth2.credentials import Credentials
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .auth import SCOPES
from .dtos.schedule import ScheduleWindow
from .errors import ConfigurationError
from .integrations import build_calendar_sink, build_task_source
from .providers.calendar_sink import CalendarSink
from .providers.task_source import TaskSource
from .settings import Settings

SERVER_NAME = "auto-calendar"

READ_ONLY = ToolAnnotations(readOnlyHint=True)


class IntegrationStatus(BaseModel):
    github_configured: bool
    google_calendar_configured: bool
    google_calendar_authorized: bool


class CalendarEntry(BaseModel):
    title: str
    start: datetime
    end: datetime
    all_day: bool


class CalendarEntries(BaseModel):
    entries: List[CalendarEntry]


class TodoItem(BaseModel):
    title: str
    status: str
    notes: Optional[str] = None
    due: Optional[str] = None


class TodoList(BaseModel):
    todos: List[TodoItem]


class TrackerItem(BaseModel):
    id: Optional[str] = None
    title: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    size: Optional[str] = None
    assignee: Optional[str] = None
    estimate: Optional[float] = None


class TrackerItems(BaseModel):
    items: List[TrackerItem]


def build_server(
    settings: Settings,
    task_source_factory: Callable[[Settings], TaskSource] = build_task_source,
    calendar_sink_factory: Callable[[Settings], CalendarSink] = build_calendar_sink,
) -> FastMCP:
    server = FastMCP(SERVER_NAME)

    @server.tool(
        name="status",
        description=(
            "Report which integrations are configured and whether Google Calendar "
            "authorisation is present. Reveals no secrets."
        ),
        annotations=READ_ONLY,
    )
    async def status() -> IntegrationStatus:
        return await asyncio.to_thread(_check_status, settings)

    @server.tool(
        name="list_calendar_entries",
        description=(
            "List calendar entries (events and all-day items) between two dates, inclusive. "
            "Dates are given as YYYY-MM-DD. Returns every matching entry in a single response; "
            "there is no cursor for paging through the result. "
            "Requires Google Calendar authorisation; call `status` first if unsure."
        ),
        annotations=READ_ONLY,
    )
    async def list_calendar_entries(start: str, end: str) -> CalendarEntries:
        return await asyncio.to_thread(
            _list_calendar_entries, settings, calendar_sink_factory, start, end
        )

    @server.tool(
        name="list_todos",
        description=(
            "List outstanding (not completed) to-do items from the configured Google Tasks "
            "list. Requires Google authorisation; call `status` first if unsure."
        ),
        annotations=READ_ONLY,
    )
    async def list_todos() -> TodoList:
        return await asyncio.to_thread(_list_todos, settings, calendar_sink_factory)

    @server.tool(
        name="list_tracker_items",
        description=(
            "List work items from the GitHub Projects tracker board, optionally restricted "
            "to the given statuses (e.g. ['Backlog', 'In Progress']). Omit `statuses` to list "
            "every item on the board. Requires GITHUB_TOKEN/GITHUB_PROJECT_ID to be configured."
        ),
        annotations=READ_ONLY,
    )
    async def list_tracker_items(statuses: Optional[List[str]] = None) -> TrackerItems:
        return await asyncio.to_thread(_list_tracker_items, settings, task_source_factory, statuses)

    return server


def _parse_date(settings: Settings, label: str, value: str) -> datetime:
    try:
        date = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ConfigurationError(
            f"Invalid {label} date: {value!r}",
            hint="Use YYYY-MM-DD, e.g. 2026-08-17.",
        ) from exc
    return datetime.combine(date, datetime.min.time(), ZoneInfo(settings.timezone))


def _list_calendar_entries(
    settings: Settings,
    calendar_sink_factory: Callable[[Settings], CalendarSink],
    start: str,
    end: str,
) -> CalendarEntries:
    window_start = _parse_date(settings, "start", start)
    window_end = _parse_date(settings, "end", end) + timedelta(days=1)
    if window_end <= window_start:
        raise ConfigurationError(
            f"end date {end!r} is before start date {start!r}",
            hint="Pass an end date on or after the start date.",
        )
    window = ScheduleWindow(start=window_start, end=window_end)

    calendar_sink = calendar_sink_factory(settings)
    entries = calendar_sink.list_entries(window)
    return CalendarEntries(
        entries=[
            CalendarEntry(title=e.title, start=e.start, end=e.end, all_day=e.all_day)
            for e in entries
        ]
    )


def _list_todos(
    settings: Settings, calendar_sink_factory: Callable[[Settings], CalendarSink]
) -> TodoList:
    calendar_sink = calendar_sink_factory(settings)
    todos = calendar_sink.list_outstanding_todos()
    return TodoList(
        todos=[TodoItem(title=t.title, status=t.status, notes=t.notes, due=t.due) for t in todos]
    )


def _list_tracker_items(
    settings: Settings,
    task_source_factory: Callable[[Settings], TaskSource],
    statuses: Optional[List[str]],
) -> TrackerItems:
    task_source = task_source_factory(settings)
    work_items = task_source.list_work_items(statuses)
    return TrackerItems(
        items=[
            TrackerItem(
                id=item.id,
                title=item.title,
                status=item.status,
                priority=item.priority.name if item.priority is not None else None,
                size=item.size.name if item.size is not None else None,
                assignee=item.assignee,
                estimate=item.estimate,
            )
            for item in work_items
        ]
    )


def _check_status(settings: Settings) -> IntegrationStatus:
    return IntegrationStatus(
        github_configured=bool(settings.github_token and settings.github_project_id),
        google_calendar_configured=settings.google_credentials_file.exists(),
        google_calendar_authorized=_has_usable_google_token(settings),
    )


def _has_usable_google_token(settings: Settings) -> bool:
    if not settings.google_token_file.exists():
        return False
    try:
        creds = Credentials.from_authorized_user_file(settings.google_token_file, SCOPES)
    except (ValueError, OSError):
        return False
    return bool(creds.valid or creds.refresh_token)
