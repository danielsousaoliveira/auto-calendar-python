from .g_cal import *
from .scheduler import schedule
from .dtos.schedule import ScheduleWindow, ScheduledBlock
from .ghub import *
from googleapiclient.errors import HttpError
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from .settings import load_settings
from .errors import AutoCalendarError
from .logger import logger


def main():
    try:
        settings = load_settings()
        creds = load_credentials(settings)
        calService = get_calendar_service(creds)
        taskService = get_tasks_service(creds)
        list_all_google_tasks(taskService, settings)
        events = list_all_google_events(calService, settings)
        token, projectId = get_github_auth(settings)
        taskSource = GitHubProjectsTaskSource(token, projectId)
        projectItems = taskSource.list_work_items()

        schedule_start = date.today()
        schedule_end = schedule_start + timedelta(days=2)
        timezone = ZoneInfo(settings.timezone)
        window = ScheduleWindow(
            datetime.combine(
                schedule_start,
                datetime.strptime(settings.working_day_start, "%H:%M").time(),
                timezone,
            ),
            datetime.combine(
                schedule_end,
                datetime.strptime(settings.working_day_end, "%H:%M").time(),
                timezone,
            ),
        )
        busy_blocks = [
            ScheduledBlock(
                title=event.get("summary", ""),
                start=datetime.fromisoformat(event["start"]["dateTime"]).astimezone(timezone),
                end=datetime.fromisoformat(event["end"]["dateTime"]).astimezone(timezone),
            )
            for event in events
            if "dateTime" in event.get("start", {}) and "dateTime" in event.get("end", {})
        ]
        plan = schedule(projectItems, busy_blocks, window)

        for task in plan.scheduled:
            event = create_event_to_insert_from_project_item(task, settings)
            insert_google_event(calService, event.to_dict(), settings)
            tasks = create_tasks_to_insert_from_project_item(task)

            for t in tasks:
                insert_google_task(taskService, t.to_dict(), settings)

            logger.info(
                f"Task '{task.title}' scheduled from {task.start} to {task.end} with priority {task.priority} and size {task.size}, estimate: {task.estimate} hours."
            )

    except HttpError as error:
        logger.error(f"An error occurred: {error}")
    except AutoCalendarError as error:
        logger.error(f"{error.args[0]} Hint: {error.hint}")


if __name__ == "__main__":
    main()
