from datetime import datetime, timedelta, timezone
import os.path
from typing import cast
from .settings import Settings, load_settings, legacy_auth_dir, warn_legacy_auth

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


def authenticate(settings: Settings | None = None):
    settings = settings or load_settings()
    creds = None
    tokenPath = settings.google_token_file
    credentialsPath = settings.google_credentials_file
    legacy = legacy_auth_dir()
    if (legacy / "credentials.json").exists() or (legacy / "token.json").exists():
        warn_legacy_auth(legacy)

    if os.path.exists(tokenPath):
        creds = Credentials.from_authorized_user_file(tokenPath, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentialsPath, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(tokenPath, "w", opener=lambda path, flags: os.open(path, flags, 0o600)) as token:
            token.write(creds.to_json())
        os.chmod(tokenPath, 0o600)

    return creds


def get_calendar_service(creds: Credentials):
    return build("calendar", "v3", credentials=creds)


def get_tasks_service(creds: Credentials):
    return build("tasks", "v1", credentials=creds)


def list_all_google_events(service, settings: Settings | None = None):
    settings = settings or load_settings()

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    print("Getting the upcoming 100 events")
    eventsResult = (
        service.events()
        .list(calendarId=settings.calendar_id, timeMin=now, maxResults=100, singleEvents=True)
        .execute()
    )
    events = eventsResult.get("items", [])

    if not events:
        print("No upcoming events found.")
    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        print(f"{event['summary']} ({start})")

    return events


def list_all_google_tasks(service, settings: Settings | None = None):
    settings = settings or load_settings()

    results = service.tasks().list(tasklist=settings.task_list_id, maxResults=100).execute()
    items = results.get("items", [])

    if not items:
        print("No tasks found.")
        return

    print("Tasks:")
    for item in items:
        print(f"{item['title']} ({item['id']}) - ({item['due']})")

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
    currentDate = datetime.strptime(startDate, "%Y-%m-%d")
    endDate = datetime.strptime(endDate, "%Y-%m-%d")

    while currentDate <= endDate:
        dayStart = parse_datetime(currentDate.strftime("%Y-%m-%d"), startHour)
        dayEnd = parse_datetime(currentDate.strftime("%Y-%m-%d"), endHour)
        window = ScheduleWindow(start=dayStart, end=dayEnd)

        for event in events:
            if (
                "dateTime" in event.get("start", {})
                and "dateTime" in event.get("end", {})
                and datetime.fromisoformat(event["start"]["dateTime"]) <= dayEnd
                and datetime.fromisoformat(event["end"]["dateTime"]) >= dayStart
            ):
                filteredEvent = ScheduledBlock(
                    title=cast(str, event["summary"]),
                    start=datetime.fromisoformat(event["start"]["dateTime"]).replace(
                        tzinfo=timezone.utc
                    ),
                    end=datetime.fromisoformat(event["end"]["dateTime"]).replace(
                        tzinfo=timezone.utc
                    ),
                    priority=None,
                    size=None,
                    estimate=None,
                    status="Backlog",
                    description="",
                    tasks=[],
                )

                scheduledBlocks.append(filteredEvent)

        largeTaskScheduled = False

        while len(tasks) > 0:
            task = tasks[0]
            assign_estimate_if_missing(task)
            taskDuration = timedelta(hours=cast(float, task.estimate))
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
                    estimate=task.estimate,
                    status="Backlog",
                    description=task.description,
                    tasks=task.tasks,
                )
                duration = (taskEnd - taskStart).total_seconds() / 3600
                scheduledTasks.append(scheduledTask)
                scheduledBlocks.append(scheduledTask)
                scheduledBlocks.sort(key=lambda x: x.start)
                if task.estimate > duration:
                    task.estimate -= duration
                else:
                    tasks.remove(task)
            else:
                break

        currentDate += timedelta(days=1)

    return scheduledTasks
