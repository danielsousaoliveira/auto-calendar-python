from typing import List
from dataclasses import asdict
from src.dtos.project_item import ProjectItemDTO
from datetime import datetime, timezone
import pickle


def dataclass_to_dict(obj):
    if hasattr(obj, "__dataclass_fields__"):
        result = asdict(obj)
        for key, value in result.items():
            if isinstance(value, list):
                result[key] = [
                    dataclass_to_dict(item) if hasattr(item, "__dataclass_fields__") else item
                    for item in value
                ]
            elif isinstance(value, dict):
                result[key] = {
                    k: dataclass_to_dict(v) if hasattr(v, "__dataclass_fields__") else v
                    for k, v in value.items()
                }
            elif hasattr(value, "__dataclass_fields__"):
                result[key] = dataclass_to_dict(value)
        return result
    return obj


def parse_response_to_list(response: dict) -> List[ProjectItemDTO]:
    projectItems = []

    nodes = response.get("data", {}).get("node", {}).get("items", {}).get("nodes", [])

    for node in nodes:
        projectItem = ProjectItemDTO(id=node["id"])
        field_content = node.get("content", {})
        field_nodes = node.get("fieldValues", {}).get("nodes", [])

        for field in field_nodes:
            field_name = field.get("field", {}).get("name")

            if field_name == "Title":
                projectItem.title = field.get("text")
            elif field_name == "Start date":
                projectItem.startDate = field.get("date")
            elif field_name == "End date":
                projectItem.endDate = field.get("date")
            elif field_name == "Priority":
                projectItem.priority = field.get("name")
            elif field_name == "Status":
                projectItem.status = field.get("name")
            elif field_name == "Size":
                projectItem.size = field.get("name")
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


def parse_datetime(dateStr, timeStr):
    return datetime.strptime(f"{dateStr} {timeStr}", "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)


def is_overlap(eventStart, eventEnd, taskStart, taskEnd):
    return not (taskEnd <= eventStart or taskStart >= eventEnd)


def find_next_available_slot(day_start, day_end, task_duration, scheduled_events):
    current_start = day_start

    for event in scheduled_events:
        event_start = event.startDate
        event_end = event.endDate

        if current_start + task_duration <= event_start:
            return current_start, current_start + task_duration
        elif current_start < event_start:
            time_available = event_start - current_start
            return current_start, current_start + time_available

        current_start = max(current_start, event_end)

    if current_start + task_duration <= day_end:
        return current_start, current_start + task_duration
    elif current_start < day_end:
        return current_start, day_end
    else:
        return None, None


def assign_estimate_if_missing(task):
    sizeToEstimate = {"XL": 8, "L": 6, "M": 4, "S": 2, "XS": 1}
    if task.estimate is None:
        task.estimate = sizeToEstimate.get(task.size, 1)


def extract_tasks(description: str) -> list:
    tasks = []
    lines = description.splitlines()

    for line in lines:
        if line.startswith("- [ ]"):
            task = line[len("- [ ] ") :].strip()
            tasks.append(task)

    return tasks


def dump_data_pickle(events, projectItems):
    with open("events.pkl", "wb") as f:
        pickle.dump(events, f)

    with open("projectItems.pkl", "wb") as f:
        pickle.dump(projectItems, f)


def load_data_pickle():
    with open("events.pkl", "rb") as f:
        events = pickle.load(f)

    with open("projectItems.pkl", "rb") as f:
        projectItems = pickle.load(f)

    return events, projectItems
