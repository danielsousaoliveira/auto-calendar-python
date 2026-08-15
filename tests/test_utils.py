import pytest
from src.utils.utils import *
from src.dtos.project_item import ProjectItemDTO
from src.dtos.task import TaskDTO, TaskLinkDTO


@pytest.fixture
def base_response():
    return {"data": {"node": {"items": {"nodes": []}}}}


@pytest.mark.parametrize(
    "fields,assignee,expected",
    [
        (
            [
                {"text": "Task A", "field": {"name": "Title"}},
                {"date": "2024-05-01", "field": {"name": "Start date"}},
                {"date": "2024-05-31", "field": {"name": "End date"}},
                {"name": "P1", "field": {"name": "Priority"}},
                {"name": "Open", "field": {"name": "Status"}},
                {"name": "S", "field": {"name": "Size"}},
                {"number": 4.0},
            ],
            [{"login": "userA"}],
            ProjectItemDTO(
                id="taskA",
                title="Task A",
                assignee="userA",
                startDate="2024-05-01",
                endDate="2024-05-31",
                priority="P1",
                status="Open",
                size="S",
                estimate=4.0,
            ),
        ),
        (
            [
                {"text": "Task B", "field": {"name": "Title"}},
                {"name": "P2", "field": {"name": "Priority"}},
            ],
            [],
            ProjectItemDTO(
                id="taskB",
                title="Task B",
                assignee=None,
                startDate=None,
                endDate=None,
                priority="P2",
                status=None,
                size=None,
                estimate=None,
            ),
        ),
        (
            [
                {"text": "Task C", "field": {"name": "Title"}},
                {"name": "P1", "field": {"name": "Priority"}},
            ],
            [{"login": "userB"}],
            ProjectItemDTO(
                id="taskC",
                title="Task C",
                assignee="userB",
                startDate=None,
                endDate=None,
                priority="P1",
                status=None,
                size=None,
                estimate=None,
            ),
        ),
    ],
)
def test_parse_response_with_param(base_response, fields, assignee, expected):
    response = base_response.copy()
    response["data"]["node"]["items"]["nodes"].append(
        {
            "id": expected.id,
            "fieldValues": {"nodes": fields},
            "content": {"title": expected.title, "assignees": {"nodes": assignee}},
        }
    )

    task_items = parse_response_to_list(response)
    assert len(task_items) == 1
    task = task_items[0]
    assert task == expected


@pytest.mark.parametrize(
    "dataclass_obj, expected_dict",
    [
        (
            TaskDTO(
                kind="task",
                title="Test Task",
                notes="These are test notes.",
                status="completed",
                due="2024-08-28",
                completed="2024-08-27",
                deleted=False,
                hidden=False,
                links=[
                    TaskLinkDTO(
                        type="related", description="Related task", link="http://example.com"
                    )
                ],
            ),
            {
                "kind": "task",
                "title": "Test Task",
                "notes": "These are test notes.",
                "status": "completed",
                "due": "2024-08-28",
                "completed": "2024-08-27",
                "deleted": False,
                "hidden": False,
                "links": [
                    {"type": "related", "description": "Related task", "link": "http://example.com"}
                ],
            },
        ),
        (
            TaskDTO(
                kind="task", title="Empty Links Task", notes="No links provided.", status="pending"
            ),
            {
                "kind": "task",
                "title": "Empty Links Task",
                "notes": "No links provided.",
                "status": "pending",
                "due": None,
                "completed": None,
                "deleted": False,
                "hidden": False,
                "links": None,
            },
        ),
    ],
)
def test_dataclass_to_dict(dataclass_obj, expected_dict):
    result = dataclass_to_dict(dataclass_obj)
    assert result == expected_dict
