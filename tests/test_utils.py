from datetime import datetime, timezone

import pytest
from src.utils.utils import *
from src.dtos.work_item import WorkItem, Priority, Size


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
            WorkItem(
                id="taskA",
                title="Task A",
                assignee="userA",
                start=datetime(2024, 5, 1, tzinfo=timezone.utc),
                end=datetime(2024, 5, 31, tzinfo=timezone.utc),
                priority=Priority.P1,
                status="Open",
                size=Size.S,
                estimate=4.0,
            ),
        ),
        (
            [
                {"text": "Task B", "field": {"name": "Title"}},
                {"name": "P2", "field": {"name": "Priority"}},
            ],
            [],
            WorkItem(
                id="taskB",
                title="Task B",
                assignee=None,
                start=None,
                end=None,
                priority=Priority.P2,
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
            WorkItem(
                id="taskC",
                title="Task C",
                assignee="userB",
                start=None,
                end=None,
                priority=Priority.P1,
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
