from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import os
from typing import cast
from .settings import Settings, load_settings, legacy_auth_dir, warn_legacy_auth
from .errors import (
    AuthorizationError,
    AuthorizationExpiredError,
    ConfigurationError,
    SchedulingError,
)
from .logger import logger

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from .dtos.event import EventDTO
from .dtos.task import TaskDTO
from .dtos.work_item import WorkItem, Priority, Size
from .dtos.schedule import ScheduleWindow, ScheduledBlock, SchedulePlan
from .utils.utils import *
import random

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/calendar", "https://www.googleapis.com/auth/tasks"]


def _check_token_permissions(token_path):
    mode = os.stat(token_path).st_mode & 0o777
    if mode & 0o077:
        raise AuthorizationError(
            f"Google token file {token_path} is readable by other users",
            hint=f"Run chmod 600 {token_path}.",
        )


def _save_credentials(creds, token_path):
    with open(token_path, "w", opener=lambda path, flags: os.open(path, flags, 0o600)) as token:
        token.write(creds.to_json())
    os.chmod(token_path, 0o600)


def load_credentials(settings: Settings | None = None):
    settings = settings or load_settings()
    creds = None
    token_path = settings.google_token_file
    legacy = legacy_auth_dir()
    if (legacy / "credentials.json").exists() or (legacy / "token.json").exists():
        warn_legacy_auth(legacy)

    if token_path.exists():
        _check_token_permissions(token_path)
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError as exc:
                raise AuthorizationExpiredError(
                    "Stored Google authorisation could not be refreshed",
                    hint="Run cal-auto-python authorize to authorise the account again.",
                ) from exc
        else:
            raise AuthorizationError(
                "Google account has not been authorised",
                hint="Run cal-auto-python authorize before starting the server.",
            )

        _save_credentials(creds, token_path)

    return creds


def authorize_credentials(settings: Settings | None = None):
    settings = settings or load_settings()
    credentials_path = settings.google_credentials_file
    if not credentials_path.exists():
        raise ConfigurationError(
            f"Missing Google OAuth client file: {credentials_path}",
            hint=(
                "Download an OAuth client ID (Desktop app) from the Google Cloud "
                f"Console and save it to {credentials_path}."
            ),
        )
    try:
        flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
        creds = flow.run_local_server(port=0)
    except Exception as exc:
        raise AuthorizationError(
            "Google Calendar/Tasks authorisation was not completed",
            hint="Rerun cal-auto-python authorize and grant access in the browser window that opens.",
        ) from exc
    _save_credentials(creds, settings.google_token_file)
    return creds


authenticate = load_credentials


def get_calendar_service(creds: Credentials):
    return build("calendar", "v3", credentials=creds)


def get_tasks_service(creds: Credentials):
    return build("tasks", "v1", credentials=creds)


def list_all_google_events(service, settings: Settings | None = None):
    settings = settings or load_settings()

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    logger.info("Getting the upcoming 100 events")
    eventsResult = (
        service.events()
        .list(calendarId=settings.calendar_id, timeMin=now, maxResults=100, singleEvents=True)
        .execute()
    )
    events = eventsResult.get("items", [])

    if not events:
        logger.info("No upcoming events found.")
    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        logger.info(f"{event['summary']} ({start})")

    return events


def list_all_google_tasks(service, settings: Settings | None = None):
    settings = settings or load_settings()

    results = service.tasks().list(tasklist=settings.task_list_id, maxResults=100).execute()
    items = results.get("items", [])

    if not items:
        logger.info("No tasks found.")
        return items

    logger.info("Tasks:")
    for item in items:
        due = item.get("due", "No due date")
        logger.info(f"{item['title']} ({item['id']}) - ({due})")

    return items


def insert_google_event(service, event, settings: Settings | None = None):
    settings = settings or load_settings()
    ev = service.events().insert(calendarId=settings.calendar_id, body=event).execute()
    return ev


def insert_google_task(service, task, settings: Settings | None = None):
    settings = settings or load_settings()
    ta = service.tasks().insert(tasklist=settings.task_list_id, body=task).execute()
    return ta


def create_tasks_to_insert_from_project_item(scheduledBlock: ScheduledBlock):
    tasks = []

    for t in scheduledBlock.tasks or []:
        kind = "tasks#task"
        status = "needsAction"
        notes = f"Event: {scheduledBlock.title}"

        tasks.append(
            TaskDTO(
                kind=kind,
                title=t,
                notes=notes,
                status=status,
                due=scheduledBlock.end.strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            )
        )

    return tasks


def create_event_to_insert_from_project_item(
    scheduledBlock: ScheduledBlock, settings: Settings | None = None
):
    settings = settings or load_settings()

    attendees = [{"email": email} for email in settings.attendees]
    colorId = str(random.randint(1, 11))
    priorityName = scheduledBlock.priority.name if scheduledBlock.priority is not None else None
    sizeName = scheduledBlock.size.name if scheduledBlock.size is not None else None
    notes = f"Priority: {priorityName} | Status: {scheduledBlock.status} | Size {sizeName} | Estimate: {scheduledBlock.estimate}"
    startDate = scheduledBlock.start.strftime("%Y-%m-%dT%H:%M:%S")
    endDate = scheduledBlock.end.strftime("%Y-%m-%dT%H:%M:%S")
    return EventDTO(
        summary=scheduledBlock.title,
        start={"dateTime": startDate, "timeZone": settings.timezone},
        end={"dateTime": endDate, "timeZone": settings.timezone},
        attendees=attendees,
        colorId=colorId,
        description=notes,
    )


def schedule_events_from_project_items(
    startDate,
    endDate,
    startHour,
    endHour,
    events,
    tasks: list[WorkItem],
    settings: Settings | None = None,
) -> SchedulePlan:
    settings = settings or load_settings()

    tasks = [task for task in tasks if task.status in settings.schedulable_statuses]
    # Sort tasks by priority: P0 > P1 > P2
    tasks.sort(
        key=lambda task: (
            task.priority if task.priority is not None else Priority.P4,
            task.size.value if task.size is not None else float("inf"),
        )
    )

    scheduledTasks: SchedulePlan = []
    scheduledBlocks: list[ScheduledBlock] = []
    local_timezone = ZoneInfo(settings.timezone)
    try:
        currentDate = datetime.strptime(startDate, "%Y-%m-%d")
        endDate = datetime.strptime(endDate, "%Y-%m-%d")
    except (TypeError, ValueError) as exc:
        raise SchedulingError(
            f"Invalid schedule window: {exc}",
            hint="Provide startDate/endDate as YYYY-MM-DD strings.",
        ) from exc

    while currentDate <= endDate:
        dayStart = parse_datetime(currentDate.strftime("%Y-%m-%d"), startHour, local_timezone)
        dayEnd = parse_datetime(currentDate.strftime("%Y-%m-%d"), endHour, local_timezone)
        window = ScheduleWindow(start=dayStart, end=dayEnd)

        for event in events:
            if "dateTime" not in event.get("start", {}) or "dateTime" not in event.get("end", {}):
                if settings.count_all_day_events and event.get("start", {}).get(
                    "date"
                ) == currentDate.strftime("%Y-%m-%d"):
                    scheduledBlocks.append(
                        ScheduledBlock(
                            title=cast(str, event.get("summary", "")),
                            start=dayStart,
                            end=dayEnd,
                            priority=None,
                            size=None,
                            estimate=None,
                            status="Backlog",
                            description="",
                            tasks=[],
                        )
                    )
                continue
            event_start = datetime.fromisoformat(event["start"]["dateTime"]).astimezone(
                local_timezone
            )
            event_end = datetime.fromisoformat(event["end"]["dateTime"]).astimezone(local_timezone)
            if event_start <= dayEnd and event_end >= dayStart:
                filteredEvent = ScheduledBlock(
                    title=cast(str, event["summary"]),
                    start=event_start,
                    end=event_end,
                    priority=None,
                    size=None,
                    estimate=None,
                    status="Backlog",
                    description="",
                    tasks=[],
                )

                scheduledBlocks.append(filteredEvent)

        scheduledBlocks = merge_overlapping_blocks(scheduledBlocks)

        largeTaskScheduled = False

        while len(tasks) > 0:
            task = tasks[0]
            remaining_estimate = estimate_for_task(task)
            taskDuration = timedelta(hours=remaining_estimate)
            switchedTasks = False
            if task.size in [Size.L, Size.XL]:
                if largeTaskScheduled:
                    for j in range(1, len(tasks)):
                        if tasks[j].size in [Size.XS, Size.S, Size.M]:
                            smaller_task = tasks.pop(j)
                            tasks.insert(0, smaller_task)
                            switchedTasks = True
                            break
                    if not switchedTasks:
                        largeTaskScheduled = False
                        currentDate += timedelta(days=1)
                        break

                else:
                    largeTaskScheduled = True

            taskStart, taskEnd = find_next_available_slot(window, taskDuration, scheduledBlocks)

            if taskStart and taskEnd:
                scheduledTask = ScheduledBlock(
                    title=cast(str, task.title),
                    start=taskStart,
                    end=taskEnd,
                    priority=task.priority,
                    size=task.size,
                    estimate=remaining_estimate,
                    status="Backlog",
                    description=task.description,
                    tasks=task.tasks,
                )
                duration = (taskEnd - taskStart).total_seconds() / 3600
                scheduledTasks.append(scheduledTask)
                scheduledBlocks.append(scheduledTask)
                scheduledBlocks.sort(key=lambda x: x.start)
                if remaining_estimate > duration:
                    task.estimate = remaining_estimate - duration
                else:
                    tasks.remove(task)
            else:
                break

        currentDate += timedelta(days=1)

    return scheduledTasks


def merge_overlapping_blocks(blocks: list[ScheduledBlock]) -> list[ScheduledBlock]:
    merged: list[ScheduledBlock] = []
    for block in sorted(blocks, key=lambda item: item.start):
        if merged and block.start <= merged[-1].end:
            merged[-1].end = max(merged[-1].end, block.end)
        else:
            merged.append(block)
    return merged
