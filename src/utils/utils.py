from typing import List, Optional
from ..dtos.work_item import WorkItem, Priority, Size, SIZE_DEFAULT_ESTIMATE_HOURS
from ..dtos.schedule import ScheduleWindow, ScheduledBlock
from datetime import datetime, timedelta, timezone


def parse_response_to_list(response: dict, source: str = "github") -> List[WorkItem]:
    projectItems = []

    nodes = response.get("data", {}).get("node", {}).get("items", {}).get("nodes", [])

    for node in nodes:
        projectItem = WorkItem(id=node["id"], source=source)
        field_content = node.get("content", {})
        field_nodes = node.get("fieldValues", {}).get("nodes", [])

        for field in field_nodes:
            field_name = field.get("field", {}).get("name")

            if field_name == "Title":
                projectItem.title = field.get("text")
            elif field_name == "Start date":
                projectItem.start = parse_tracker_date(field.get("date"))
            elif field_name == "End date":
                projectItem.end = parse_tracker_date(field.get("date"))
            elif field_name == "Priority":
                projectItem.priority = Priority[field.get("name")]
            elif field_name == "Status":
                projectItem.status = field.get("name")
            elif field_name == "Size":
                projectItem.size = Size[field.get("name")]
            elif field.get("number"):
                projectItem.estimate = field.get("number")

        assignees = node.get("content", {}).get("assignees", {}).get("nodes", [])
        if len(assignees) > 0 and "login" in assignees[0]:
            projectItem.assignee = assignees[0]["login"]
        else:
            projectItem.assignee = None

        description = field_content.get("body", "")
        if description:
            projectItem.description = description
            projectItem.tasks = extract_tasks(description)

        projectItems.append(projectItem)

    return projectItems


def parse_tracker_date(dateStr: Optional[str]) -> Optional[datetime]:
    if dateStr is None:
        return None
    return datetime.strptime(dateStr, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def parse_datetime(dateStr, timeStr, tz=timezone.utc):
    return datetime.strptime(f"{dateStr} {timeStr}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)


def find_next_available_slot(
    window: ScheduleWindow, task_duration: timedelta, scheduled_blocks: List[ScheduledBlock]
):
    current_start = window.start

    for block in scheduled_blocks:
        block_start = block.start
        block_end = block.end

        if current_start + task_duration <= block_start:
            return current_start, current_start + task_duration
        elif current_start < block_start:
            time_available = block_start - current_start
            return current_start, current_start + time_available

        current_start = max(current_start, block_end)

    if current_start + task_duration <= window.end:
        return current_start, current_start + task_duration
    elif current_start < window.end:
        return current_start, window.end
    else:
        return None, None


def estimate_for_task(task: WorkItem):
    return (
        task.estimate
        if task.estimate is not None
        else (SIZE_DEFAULT_ESTIMATE_HOURS.get(task.size, 1.0) if task.size is not None else 1.0)
    )


def extract_tasks(description: str) -> list:
    tasks = []
    lines = description.splitlines()

    for line in lines:
        if line.startswith("- [ ]"):
            task = line[len("- [ ] ") :].strip()
            tasks.append(task)

    return tasks
