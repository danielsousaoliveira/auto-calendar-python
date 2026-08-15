from .g_cal import *
from .ghub import *
from googleapiclient.errors import HttpError
from datetime import date, timedelta
from .settings import load_settings


def main():
    settings = load_settings()

    creds = authenticate(settings)
    try:
        calService = get_calendar_service(creds)
        taskService = get_tasks_service(creds)
        list_all_google_tasks(taskService, settings)
        events = list_all_google_events(calService, settings)
        token, projectId = get_github_auth(settings)
        projectItems = get_github_project_items(token, projectId)

        schedule_start = date.today()
        schedule_end = schedule_start + timedelta(days=2)
        scheduledTasks = schedule_events_from_project_items(
            schedule_start.isoformat(),
            schedule_end.isoformat(),
            settings.working_day_start,
            settings.working_day_end,
            events,
            projectItems,
            settings,
        )

        for task in scheduledTasks:
            event = create_event_to_insert_from_project_item(task, settings)
            insert_google_event(calService, event.to_dict(), settings)
            tasks = create_tasks_to_insert_from_project_item(task)

            for t in tasks:
                insert_google_task(taskService, t.to_dict(), settings)

            print(
                f"Task '{task.title}' scheduled from {task.start} to {task.end} with priority {task.priority} and size {task.size}, estimate: {task.estimate} hours."
            )

    except HttpError as error:
        print(f"An error occurred: {error}")


if __name__ == "__main__":
    main()
