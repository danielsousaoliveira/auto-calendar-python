from .g_cal import *
from .ghub import *
from googleapiclient.errors import HttpError


def main():

    creds = authenticate()
    try:
        calService = get_calendar_service(creds)
        taskService = get_tasks_service(creds)
        list_all_google_tasks(taskService)
        events = list_all_google_events(calService)
        token, projectId = get_github_auth()
        projectItems = get_github_project_items(token, projectId)

        display_github_project_items(projectItems)

        scheduledTasks = schedule_events_from_project_items(
            "2024-09-05", "2024-09-07", "09:00", "17:00", events, projectItems
        )

        for task in scheduledTasks:
            event = create_event_to_insert_from_project_item(task)
            insert_google_event(calService, event.to_dict())
            tasks = create_tasks_to_insert_from_project_item(task)

            for t in tasks:
                insert_google_task(taskService, t.to_dict())

            print(
                f"Task '{task.title}' scheduled from {task.startDate} to {task.endDate} with priority {task.priority} and size {task.size}, estimate: {task.estimate} hours."
            )

    except HttpError as error:
        print(f"An error occurred: {error}")


if __name__ == "__main__":
    main()
