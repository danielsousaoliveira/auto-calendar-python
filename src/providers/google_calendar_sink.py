import hashlib
from datetime import datetime, timezone
from typing import List, Optional, cast
from zoneinfo import ZoneInfo

from ..dtos.event import EventDTO
from ..dtos.schedule import ScheduledBlock, ScheduleWindow
from ..dtos.task import TaskDTO
from ..settings import Settings, load_settings
from .calendar_sink import CalendarSink

EVENT_COLOR_COUNT = 11


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
        event_date = start.get("date")
        if event_date is None:
            return None
        if not (
            window.start.date()
            <= datetime.strptime(event_date, "%Y-%m-%d").date()
            <= window.end.date()
        ):
            return None
        return ScheduledBlock(
            title=cast(str, event.get("summary", "")),
            start=window.start,
            end=window.end,
            status="Backlog",
        )

    event_start = datetime.fromisoformat(start["dateTime"]).astimezone(local_timezone)
    event_end = datetime.fromisoformat(end["dateTime"]).astimezone(local_timezone)
    if event_start > window.end or event_end < window.start:
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
    )


def build_todos(block: ScheduledBlock) -> List[TaskDTO]:
    return [
        TaskDTO(
            kind="tasks#task",
            title=item,
            notes=f"Event: {block.title}",
            status="needsAction",
            due=block.end.strftime("%Y-%m-%dT%H:%M:%S") + "Z",
        )
        for item in block.tasks or []
    ]


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
        result = (
            self.calendar_service.events()
            .list(
                calendarId=self.settings.calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=100,
                singleEvents=True,
            )
            .execute()
        )
        return result.get("items", [])

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

    def find_existing_event(self, title: str, window: ScheduleWindow) -> Optional[dict]:
        for event in self.list_events(window):
            if event.get("summary") == title:
                return event
        return None
