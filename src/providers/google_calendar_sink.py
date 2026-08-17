import hashlib
import re
from datetime import datetime, timezone
from typing import List, Optional, Set, cast
from zoneinfo import ZoneInfo

from ..dtos.event import EventDTO
from ..dtos.schedule import ScheduledBlock, ScheduleWindow
from ..dtos.task import TaskDTO
from ..settings import Settings, load_settings
from .calendar_sink import CalendarSink

EVENT_COLOR_COUNT = 11

TODO_MARKER_PATTERN = re.compile(r"\[auto-calendar:[^:\]]+:[^:\]]+:\d+\]")


def todo_marker(source: Optional[str], source_id: Optional[str], index: int) -> Optional[str]:
    if not source or not source_id:
        return None
    return f"[auto-calendar:{source}:{source_id}:{index}]"


def block_identity(
    source: Optional[str], source_id: Optional[str], start: Optional[datetime]
) -> Optional[str]:
    if not source or not source_id or start is None:
        return None
    return f"{source}:{source_id}:{start.isoformat()}"


def event_color_id(source_id: str) -> str:
    digest = hashlib.sha256(source_id.encode("utf-8")).digest()
    return str((digest[0] % EVENT_COLOR_COUNT) + 1)


def event_to_busy_block(
    event: dict, window: ScheduleWindow, settings: Settings
) -> Optional[ScheduledBlock]:
    start = event.get("start", {})
    end = event.get("end", {})
    local_timezone = ZoneInfo(settings.timezone)

    if "dateTime" not in start or "dateTime" not in end:
        if not settings.count_all_day_events:
            return None
        event_start_date = start.get("date")
        event_end_date = end.get("date")
        if event_start_date is None or event_end_date is None:
            return None
        # Google's all-day "end.date" is exclusive: an event spanning Jan 1-3 has
        # start.date=2024-01-01, end.date=2024-01-03 and does not occupy Jan 3.
        span_start = datetime.strptime(event_start_date, "%Y-%m-%d").date()
        span_end = datetime.strptime(event_end_date, "%Y-%m-%d").date()
        if span_start > window.end.date() or span_end <= window.start.date():
            return None
        return ScheduledBlock(
            title=cast(str, event.get("summary", "")),
            start=window.start,
            end=window.end,
            status="Backlog",
        )

    event_start = datetime.fromisoformat(start["dateTime"]).astimezone(local_timezone)
    event_end = datetime.fromisoformat(end["dateTime"]).astimezone(local_timezone)
    if event_start >= window.end or event_end <= window.start:
        return None

    return ScheduledBlock(
        title=cast(str, event.get("summary", "")),
        start=event_start,
        end=event_end,
        status="Backlog",
    )


def _merge_busy_blocks(blocks: List[ScheduledBlock]) -> List[ScheduledBlock]:
    merged: List[ScheduledBlock] = []
    for block in sorted(blocks, key=lambda item: item.start):
        if merged and block.start <= merged[-1].end:
            merged[-1].end = max(merged[-1].end, block.end)
        else:
            merged.append(block)
    return merged


def build_event(block: ScheduledBlock, settings: Settings) -> EventDTO:
    attendees = [{"email": email} for email in settings.attendees]
    priority_name = block.priority.name if block.priority is not None else None
    size_name = block.size.name if block.size is not None else None
    notes = (
        f"Priority: {priority_name} | Status: {block.status} | "
        f"Size {size_name} | Estimate: {block.estimate}"
    )
    extended_properties = None
    identity = block_identity(block.source, block.source_id, block.start)
    if identity and block.source and block.source_id:
        extended_properties = {
            "private": {
                "source_system": block.source,
                "source_id": block.source_id,
                "auto_calendar_id": identity,
            }
        }
    return EventDTO(
        summary=block.title,
        start={
            "dateTime": block.start.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": settings.timezone,
        },
        end={
            "dateTime": block.end.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": settings.timezone,
        },
        attendees=attendees or None,
        colorId=event_color_id(block.source_id or block.title),
        description=notes,
        extendedProperties=extended_properties,
    )


def build_todos(block: ScheduledBlock) -> List[TaskDTO]:
    todos = []
    for index, item in enumerate(block.tasks or []):
        marker = todo_marker(block.source, block.source_id, index)
        notes = f"Event: {block.title}"
        if marker:
            notes = f"{notes} {marker}"
        todos.append(
            TaskDTO(
                kind="tasks#task",
                title=item,
                notes=notes,
                status="needsAction",
                due=block.end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            )
        )
    return todos


class GoogleCalendarSink(CalendarSink):
    def __init__(
        self, calendar_service, tasks_service, settings: Optional[Settings] = None
    ) -> None:
        self.calendar_service = calendar_service
        self.tasks_service = tasks_service
        self.settings = settings or load_settings()

    def list_events(self, window: ScheduleWindow) -> List[dict]:
        time_min = window.start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        time_max = window.end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        items: List[dict] = []
        page_token = None
        while True:
            result = (
                self.calendar_service.events()
                .list(
                    calendarId=self.settings.calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=100,
                    singleEvents=True,
                    pageToken=page_token,
                )
                .execute()
            )
            items.extend(result.get("items", []))
            page_token = result.get("nextPageToken")
            if not page_token:
                return items

    def list_busy_blocks(self, window: ScheduleWindow) -> List[ScheduledBlock]:
        blocks = [
            block
            for block in (
                event_to_busy_block(event, window, self.settings)
                for event in self.list_events(window)
            )
            if block is not None
        ]
        return _merge_busy_blocks(blocks)

    def create_event(self, event: EventDTO) -> dict:
        return (
            self.calendar_service.events()
            .insert(calendarId=self.settings.calendar_id, body=event.to_dict())
            .execute()
        )

    def create_todo(self, task: TaskDTO) -> dict:
        return (
            self.tasks_service.tasks()
            .insert(tasklist=self.settings.task_list_id, body=task.to_dict())
            .execute()
        )

    def has_scheduled_event(self, source: str, source_id: str, start: datetime) -> bool:
        identity = block_identity(source, source_id, start)
        result = (
            self.calendar_service.events()
            .list(
                calendarId=self.settings.calendar_id,
                privateExtendedProperty=[f"auto_calendar_id={identity}"],
                maxResults=1,
            )
            .execute()
        )
        return bool(result.get("items"))

    def list_scheduled_todo_markers(self) -> Set[str]:
        markers: Set[str] = set()
        page_token = None
        while True:
            result = (
                self.tasks_service.tasks()
                .list(
                    tasklist=self.settings.task_list_id,
                    showCompleted=True,
                    showHidden=True,
                    pageToken=page_token,
                )
                .execute()
            )
            for task in result.get("items", []):
                match = TODO_MARKER_PATTERN.search(task.get("notes") or "")
                if match:
                    markers.add(match.group(0))
            page_token = result.get("nextPageToken")
            if not page_token:
                return markers
