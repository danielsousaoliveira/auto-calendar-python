"""MCP server exposing this tool's capabilities to an assistant."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta
from typing import Callable, List, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from google.oauth2.credentials import Credentials
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .auth import SCOPES
from .dtos.event import EventDTO
from .dtos.schedule import ScheduleWindow, ScheduledBlock
from .dtos.work_item import Priority, Size, WorkItem
from .dtos.task import TaskDTO
from .errors import ConfigurationError
from .integrations import build_calendar_sink, build_task_source
from .providers.calendar_sink import CalendarSink
from .providers.task_source import TaskSource
from .settings import Settings
from .scheduler import schedule
from .sync import SyncResult, run_sync

SERVER_NAME = "auto-calendar"

READ_ONLY = ToolAnnotations(readOnlyHint=True)
WRITES_EXTERNAL_SYSTEM = ToolAnnotations(
    readOnlyHint=False, idempotentHint=False, destructiveHint=False, openWorldHint=True
)


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


class PlanningItem(BaseModel):
    title: str
    priority: Optional[str] = None
    size: Optional[str] = None
    estimate: Optional[float] = None
    id: Optional[str] = None


class PlanningCommitment(BaseModel):
    title: str
    start: datetime
    end: datetime


class PlannedBlock(BaseModel):
    title: str
    start: datetime
    end: datetime
    source_id: Optional[str] = None


class UnplannedItem(BaseModel):
    title: str
    reason: str


class WeekPlan(BaseModel):
    scheduled: List[PlannedBlock]
    unscheduled: List[UnplannedItem]


class SyncBlock(BaseModel):
    title: str
    start: datetime
    end: datetime
    source_id: Optional[str] = None


class SyncReport(BaseModel):
    summary: str
    preview: bool
    planned: List[SyncBlock]
    created: List[SyncBlock]
    skipped: List[SyncBlock]
    unscheduled: List[UnplannedItem]


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

    @server.tool(
        name="plan_week",
        description=(
            "Plan work into free working-hour slots for a date range. Accepts work and existing "
            "commitments directly and does not access configured accounts, network services, or "
            "persist the plan. Returns both scheduled and unscheduled work."
        ),
        annotations=READ_ONLY,
    )
    async def plan_week(
        items: List[PlanningItem],
        start_date: str,
        end_date: str,
        working_day_start: str,
        working_day_end: str,
        timezone: Optional[str] = None,
        commitments: Optional[List[PlanningCommitment]] = None,
    ) -> WeekPlan:
        return await asyncio.to_thread(
            _plan_week,
            items,
            start_date,
            end_date,
            working_day_start,
            working_day_end,
            timezone,
            commitments or [],
        )

    @server.tool(
        name="sync_backlog",
        description=(
            "Fetch the schedulable backlog, fit it around existing calendar commitments, and "
            "return the complete result. Preview by default; pass apply=true explicitly to "
            "create calendar events and to-dos. Existing entries are skipped."
        ),
        annotations=WRITES_EXTERNAL_SYSTEM,
    )
    async def sync_backlog(
        start_date: str,
        end_date: str,
        apply: bool = False,
    ) -> SyncReport:
        return await asyncio.to_thread(
            _sync_backlog,
            settings,
            task_source_factory,
            calendar_sink_factory,
            start_date,
            end_date,
            apply,
        )

    @server.tool(
        name="create_calendar_entry",
        description=(
            "Create exactly one calendar entry with a summary, start, end, and optional "
            "description and attendee email addresses. Start and end use ISO 8601 values; "
            "a naive value is interpreted in the supplied IANA timezone. This writes to "
            "Google Calendar and does not schedule or deduplicate entries."
        ),
        annotations=WRITES_EXTERNAL_SYSTEM,
    )
    async def create_calendar_entry(
        summary: str,
        start: str,
        end: str,
        timezone: str,
        description: Optional[str] = None,
        attendees: Optional[List[str]] = None,
    ) -> dict:
        return await asyncio.to_thread(
            _create_calendar_entry,
            settings,
            calendar_sink_factory,
            summary,
            start,
            end,
            timezone,
            description,
            attendees,
        )

    @server.tool(
        name="create_todo",
        description=(
            "Create exactly one to-do with a title and optional note and due date. "
            "The due date must be an ISO 8601 value when supplied. This writes to Google "
            "Tasks and does not deduplicate items."
        ),
        annotations=WRITES_EXTERNAL_SYSTEM,
    )
    async def create_todo(
        title: str, note: Optional[str] = None, due: Optional[str] = None
    ) -> dict:
        return await asyncio.to_thread(
            _create_todo, settings, calendar_sink_factory, title, note, due
        )

    return server


def _plan_week(
    items: List[PlanningItem],
    start_date: str,
    end_date: str,
    working_day_start: str,
    working_day_end: str,
    timezone: Optional[str],
    commitments: List[PlanningCommitment],
) -> WeekPlan:
    zone = ZoneInfo(timezone or "UTC")
    first = date.fromisoformat(start_date)
    last = date.fromisoformat(end_date)
    start_clock = time.fromisoformat(working_day_start)
    end_clock = time.fromisoformat(working_day_end)
    window = ScheduleWindow(
        datetime.combine(first, start_clock, zone), datetime.combine(last, end_clock, zone)
    )
    if window.end <= window.start:
        raise ConfigurationError(
            "The planning date range and working hours must form a positive window",
            hint="Use an end date on or after the start date and valid working hours.",
        )
    work = [
        WorkItem(
            id=item.id,
            title=item.title,
            priority=Priority[item.priority] if item.priority else None,
            size=Size[item.size] if item.size else None,
            estimate=item.estimate,
        )
        for item in items
    ]
    busy = []
    for commitment in commitments:
        start = _normalize_commitment_datetime(commitment.start, zone)
        end = _normalize_commitment_datetime(commitment.end, zone)
        if end <= start:
            raise ConfigurationError(
                f"Commitment {commitment.title!r} must end after it starts",
                hint="Provide a commitment with an end datetime after its start datetime.",
            )
        busy.append(ScheduledBlock(title=commitment.title, start=start, end=end))
    result = schedule(work, busy, window)
    return WeekPlan(
        scheduled=[
            PlannedBlock(
                title=block.title, start=block.start, end=block.end, source_id=block.source_id
            )
            for block in result.scheduled
        ],
        unscheduled=[
            UnplannedItem(title=item.work_item.title or "", reason=item.reason)
            for item in result.unscheduled
        ],
    )


def _normalize_commitment_datetime(value: datetime, zone: ZoneInfo) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=zone)
    return value.astimezone(zone)


def _sync_backlog(
    settings: Settings,
    task_source_factory: Callable[[Settings], TaskSource],
    calendar_sink_factory: Callable[[Settings], CalendarSink],
    start_date: str,
    end_date: str,
    apply: bool,
) -> SyncReport:
    try:
        first = date.fromisoformat(start_date)
        last = date.fromisoformat(end_date)
        start_clock = time.fromisoformat(settings.working_day_start)
        end_clock = time.fromisoformat(settings.working_day_end)
    except ValueError as exc:
        raise ConfigurationError(
            "Invalid sync date", hint="Use YYYY-MM-DD for start_date and end_date."
        ) from exc
    zone = ZoneInfo(settings.timezone)
    window_start = datetime.combine(first, start_clock, zone)
    window_end = datetime.combine(last, end_clock, zone)
    if window_end <= window_start:
        raise ConfigurationError(
            f"end date {end_date!r} is before start date {start_date!r}",
            hint="Pass an end date on or after the start date.",
        )
    result = run_sync(
        task_source_factory(settings),
        calendar_sink_factory(settings),
        ScheduleWindow(window_start, window_end),
        settings,
        apply=apply,
    )
    return _sync_report(result, apply)


def _sync_report(result: SyncResult, apply: bool) -> SyncReport:
    def block(value: ScheduledBlock) -> SyncBlock:
        return SyncBlock(
            title=value.title, start=value.start, end=value.end, source_id=value.source_id
        )

    planned = [block(value) for value in result.scheduled]
    created = [block(value) for value in result.created]
    skipped = [block(value) for value in result.skipped]
    unscheduled = [
        UnplannedItem(title=value.work_item.title or "", reason=value.reason)
        for value in result.unscheduled
    ]
    mode = "Created" if apply else "Planned"
    summary = (
        f"{mode} {len(created) if apply else len(planned)} item(s); "
        f"skipped {len(skipped)} already present; "
        f"could not place {len(unscheduled)}."
    )
    return SyncReport(
        summary=summary,
        preview=not apply,
        planned=planned,
        created=created,
        skipped=skipped,
        unscheduled=unscheduled,
    )


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


def _parse_datetime(value: str, label: str, timezone: str) -> datetime:
    try:
        zone = ZoneInfo(timezone)
    except Exception as exc:
        raise ConfigurationError(
            f"Unknown timezone: {timezone!r}",
            hint="Pass a valid IANA timezone name, e.g. Europe/Lisbon.",
        ) from exc
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConfigurationError(
            f"Invalid {label} datetime: {value!r}",
            hint="Use an ISO 8601 datetime, e.g. 2026-08-18T09:00:00.",
        ) from exc
    return parsed.replace(tzinfo=zone) if parsed.tzinfo is None else parsed


def _create_calendar_entry(
    settings: Settings,
    calendar_sink_factory: Callable[[Settings], CalendarSink],
    summary: str,
    start: str,
    end: str,
    timezone: str,
    description: Optional[str],
    attendees: Optional[List[str]],
) -> dict:
    if not summary.strip():
        raise ConfigurationError("Calendar summary cannot be empty", hint="Pass a summary.")
    start_dt = _parse_datetime(start, "start", timezone)
    end_dt = _parse_datetime(end, "end", timezone)
    if end_dt <= start_dt:
        raise ConfigurationError(
            "Calendar entry end must be after its start",
            hint="Pass an end datetime later than the start datetime.",
        )
    event = EventDTO(
        summary=summary,
        start={"dateTime": start_dt.isoformat(), "timeZone": timezone},
        end={"dateTime": end_dt.isoformat(), "timeZone": timezone},
        description=description,
        attendees=[{"email": email} for email in (attendees or [])] or None,
    )
    return calendar_sink_factory(settings).create_event(event)


def _create_todo(
    settings: Settings,
    calendar_sink_factory: Callable[[Settings], CalendarSink],
    title: str,
    note: Optional[str],
    due: Optional[str],
) -> dict:
    if not title.strip():
        raise ConfigurationError("To-do title cannot be empty", hint="Pass a title.")
    if due is not None:
        try:
            if len(due) == 10:
                due = datetime.strptime(due, "%Y-%m-%d").isoformat() + "Z"
            else:
                datetime.fromisoformat(due.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ConfigurationError(
                f"Invalid due datetime: {due!r}", hint="Use an ISO 8601 datetime."
            ) from exc
    task = TaskDTO(kind="tasks#task", title=title, notes=note or "", status="needsAction", due=due)
    return calendar_sink_factory(settings).create_todo(task)


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
