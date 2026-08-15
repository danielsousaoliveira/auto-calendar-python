from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from googleapiclient.errors import HttpError

from .auth import get_calendar_service, get_tasks_service, load_credentials
from .dtos.schedule import ScheduleWindow
from .errors import AutoCalendarError
from .ghub import GitHubProjectsTaskSource, get_github_auth
from .logger import logger
from .providers.google_calendar_sink import (
    GoogleCalendarSink,
    build_event,
    build_todos,
    todo_marker,
)
from .scheduler import schedule
from .settings import load_settings


def main():
    try:
        settings = load_settings()
        creds = load_credentials(settings)
        calService = get_calendar_service(creds)
        taskService = get_tasks_service(creds)
        sink = GoogleCalendarSink(calService, taskService, settings)

        tz = ZoneInfo(settings.timezone)
        schedule_start = datetime.now(tz).date()
        schedule_end = schedule_start + timedelta(days=2)
        window = ScheduleWindow(
            start=datetime.combine(
                schedule_start,
                datetime.strptime(settings.working_day_start, "%H:%M").time(),
                tz,
            ),
            end=datetime.combine(
                schedule_end,
                datetime.strptime(settings.working_day_end, "%H:%M").time(),
                tz,
            ),
        )
        busy_blocks = sink.list_busy_blocks(window)

        token, projectId = get_github_auth(settings)
        taskSource = GitHubProjectsTaskSource(token, projectId)
        projectItems = taskSource.list_work_items()

        plan = schedule(projectItems, busy_blocks, window)
        existing_todo_markers = sink.list_scheduled_todo_markers()

        for task in plan.scheduled:
            if not (
                task.source
                and task.source_id
                and sink.has_scheduled_event(task.source, task.source_id)
            ):
                event = build_event(task, settings)
                sink.create_event(event)

            for index, todo in enumerate(build_todos(task)):
                marker = todo_marker(task.source, task.source_id, index)
                if marker and marker in existing_todo_markers:
                    continue
                sink.create_todo(todo)
                if marker:
                    existing_todo_markers.add(marker)

            logger.info(
                f"Task '{task.title}' scheduled from {task.start} to {task.end} with priority {task.priority} and size {task.size}, estimate: {task.estimate} hours."
            )

    except HttpError as error:
        logger.error(f"An error occurred: {error}")
    except AutoCalendarError as error:
        logger.error(f"{error.args[0]} Hint: {error.hint}")


if __name__ == "__main__":
    main()
