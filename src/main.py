from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from googleapiclient.errors import HttpError

from .auth import get_calendar_service, get_tasks_service, load_credentials
from .dtos.schedule import ScheduleWindow
from .errors import AutoCalendarError
from .ghub import GitHubProjectsTaskSource, get_github_auth
from .logger import logger
from .providers.google_calendar_sink import GoogleCalendarSink, build_event, build_todos
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
        schedule_start = date.today()
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

        for task in plan.scheduled:
            event = build_event(task, settings)
            sink.create_event(event)

            for todo in build_todos(task):
                sink.create_todo(todo)

            logger.info(
                f"Task '{task.title}' scheduled from {task.start} to {task.end} with priority {task.priority} and size {task.size}, estimate: {task.estimate} hours."
            )

    except HttpError as error:
        logger.error(f"An error occurred: {error}")
    except AutoCalendarError as error:
        logger.error(f"{error.args[0]} Hint: {error.hint}")


if __name__ == "__main__":
    main()
