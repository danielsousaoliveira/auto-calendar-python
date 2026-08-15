from datetime import datetime, timezone

import pytest

from src.dtos.event import EventDTO
from src.dtos.schedule import ScheduledBlock, ScheduleWindow
from src.dtos.task import TaskDTO
from src.providers.google_calendar_sink import (
    GoogleCalendarSink,
    build_event,
    build_todos,
    event_color_id,
    event_to_busy_block,
    todo_marker,
)
from src.settings import load_settings


def settings(tmp_path, **overrides):
    env = {"CAL_AUTO_CONFIG_DIR": str(tmp_path), "CAL_AUTO_TIMEZONE": "UTC"}
    env.update(overrides)
    return load_settings(env)


def window():
    return ScheduleWindow(
        start=datetime(2024, 1, 1, 9, tzinfo=timezone.utc),
        end=datetime(2024, 1, 1, 17, tzinfo=timezone.utc),
    )


def test_event_to_busy_block_converts_a_zero_offset_event(tmp_path):
    event = {
        "summary": "Meeting",
        "start": {"dateTime": "2024-01-01T10:00:00+00:00"},
        "end": {"dateTime": "2024-01-01T11:00:00+00:00"},
    }

    block = event_to_busy_block(event, window(), settings(tmp_path))

    assert block == ScheduledBlock(
        title="Meeting",
        start=datetime(2024, 1, 1, 10, tzinfo=timezone.utc),
        end=datetime(2024, 1, 1, 11, tzinfo=timezone.utc),
        status="Backlog",
    )


def test_event_to_busy_block_converts_a_non_zero_offset_event_into_the_configured_timezone(
    tmp_path,
):
    event = {
        "summary": "Meeting",
        "start": {"dateTime": "2024-01-01T10:00:00+01:00"},
        "end": {"dateTime": "2024-01-01T11:00:00+01:00"},
    }

    block = event_to_busy_block(event, window(), settings(tmp_path))

    assert block.start == datetime(2024, 1, 1, 9, tzinfo=timezone.utc)
    assert block.end == datetime(2024, 1, 1, 10, tzinfo=timezone.utc)


def test_event_to_busy_block_skips_events_outside_the_window(tmp_path):
    event = {
        "summary": "Later",
        "start": {"dateTime": "2024-01-02T10:00:00+00:00"},
        "end": {"dateTime": "2024-01-02T11:00:00+00:00"},
    }

    assert event_to_busy_block(event, window(), settings(tmp_path)) is None


def test_event_to_busy_block_skips_all_day_events_by_default(tmp_path):
    event = {"summary": "Holiday", "start": {"date": "2024-01-01"}, "end": {"date": "2024-01-02"}}

    assert event_to_busy_block(event, window(), settings(tmp_path)) is None


def test_event_to_busy_block_blocks_the_whole_window_for_all_day_events_when_enabled(tmp_path):
    event = {"summary": "Holiday", "start": {"date": "2024-01-01"}, "end": {"date": "2024-01-02"}}

    block = event_to_busy_block(
        event, window(), settings(tmp_path, CAL_AUTO_COUNT_ALL_DAY_EVENTS="true")
    )

    assert block == ScheduledBlock(
        title="Holiday", start=window().start, end=window().end, status="Backlog"
    )


def test_event_to_busy_block_matches_a_multi_day_all_day_event_on_a_later_window_day(tmp_path):
    event = {"summary": "Trip", "start": {"date": "2024-01-02"}, "end": {"date": "2024-01-04"}}
    multi_day_window = ScheduleWindow(
        start=datetime(2024, 1, 3, 9, tzinfo=timezone.utc),
        end=datetime(2024, 1, 3, 17, tzinfo=timezone.utc),
    )

    block = event_to_busy_block(
        event, multi_day_window, settings(tmp_path, CAL_AUTO_COUNT_ALL_DAY_EVENTS="true")
    )

    assert block is not None


def test_event_to_busy_block_excludes_the_all_day_event_end_date(tmp_path):
    event = {"summary": "Holiday", "start": {"date": "2024-01-01"}, "end": {"date": "2024-01-02"}}
    day_after_window = ScheduleWindow(
        start=datetime(2024, 1, 2, 9, tzinfo=timezone.utc),
        end=datetime(2024, 1, 2, 17, tzinfo=timezone.utc),
    )

    block = event_to_busy_block(
        event, day_after_window, settings(tmp_path, CAL_AUTO_COUNT_ALL_DAY_EVENTS="true")
    )

    assert block is None


def test_event_color_id_is_deterministic_for_the_same_source_item():
    assert event_color_id("item-1") == event_color_id("item-1")


def test_event_color_id_differs_for_different_source_items():
    assert event_color_id("item-1") != event_color_id("item-2")


def test_build_event_omits_empty_fields(tmp_path):
    block = ScheduledBlock(
        title="A",
        start=datetime(2024, 1, 1, 9, tzinfo=timezone.utc),
        end=datetime(2024, 1, 1, 11, tzinfo=timezone.utc),
        source_id="item-1",
    )

    dto = build_event(block, settings(tmp_path))

    assert "attendees" not in dto.to_dict()
    assert dto.to_dict()["colorId"] == event_color_id("item-1")


def test_build_event_includes_configured_attendees(tmp_path):
    block = ScheduledBlock(
        title="A",
        start=datetime(2024, 1, 1, 9, tzinfo=timezone.utc),
        end=datetime(2024, 1, 1, 11, tzinfo=timezone.utc),
        source_id="item-1",
    )

    dto = build_event(block, settings(tmp_path, CAL_AUTO_ATTENDEES="a@example.com"))

    assert dto.to_dict()["attendees"] == [{"email": "a@example.com"}]


def test_build_todos_creates_one_task_per_checkbox():
    block = ScheduledBlock(
        title="A",
        start=datetime(2024, 1, 1, 9, tzinfo=timezone.utc),
        end=datetime(2024, 1, 1, 11, tzinfo=timezone.utc),
        tasks=["Do X", "Do Y"],
    )

    todos = build_todos(block)

    assert [t.title for t in todos] == ["Do X", "Do Y"]


def test_build_todos_embeds_a_marker_per_checkbox_when_source_is_known():
    block = ScheduledBlock(
        title="A",
        start=datetime(2024, 1, 1, 9, tzinfo=timezone.utc),
        end=datetime(2024, 1, 1, 11, tzinfo=timezone.utc),
        tasks=["Do X", "Do Y"],
        source="github",
        source_id="item-1",
    )

    todos = build_todos(block)

    assert todo_marker("github", "item-1", 0) in todos[0].notes
    assert todo_marker("github", "item-1", 1) in todos[1].notes
    assert todos[0].notes != todos[1].notes


def test_build_todos_omits_marker_without_a_source_id():
    block = ScheduledBlock(
        title="A",
        start=datetime(2024, 1, 1, 9, tzinfo=timezone.utc),
        end=datetime(2024, 1, 1, 11, tzinfo=timezone.utc),
        tasks=["Do X"],
    )

    todos = build_todos(block)

    assert todos[0].notes == "Event: A"


def test_build_event_carries_source_metadata_as_private_extended_properties(tmp_path):
    block = ScheduledBlock(
        title="A",
        start=datetime(2024, 1, 1, 9, tzinfo=timezone.utc),
        end=datetime(2024, 1, 1, 11, tzinfo=timezone.utc),
        source="github",
        source_id="item-1",
    )

    dto = build_event(block, settings(tmp_path))

    assert dto.to_dict()["extendedProperties"] == {
        "private": {"source_system": "github", "source_id": "item-1"}
    }


def test_event_dto_rejects_an_empty_summary():
    with pytest.raises(ValueError, match="non-empty summary"):
        EventDTO(
            summary="",
            start={"dateTime": "x", "timeZone": "UTC"},
            end={"dateTime": "x", "timeZone": "UTC"},
        )


def test_task_dto_rejects_an_empty_title():
    with pytest.raises(ValueError, match="non-empty title"):
        TaskDTO(kind="tasks#task", title="", notes="", status="needsAction")


def test_list_busy_blocks_uses_the_configured_calendar(tmp_path, mocker):
    service = mocker.Mock()
    service.events.return_value.list.return_value.execute.return_value = {
        "items": [
            {
                "summary": "Meeting",
                "start": {"dateTime": "2024-01-01T10:00:00+00:00"},
                "end": {"dateTime": "2024-01-01T11:00:00+00:00"},
            }
        ]
    }
    sink = GoogleCalendarSink(
        service, mocker.Mock(), settings(tmp_path, CAL_AUTO_CALENDAR_ID="work")
    )

    blocks = sink.list_busy_blocks(window())

    assert [b.title for b in blocks] == ["Meeting"]
    _, kwargs = service.events.return_value.list.call_args
    assert kwargs["calendarId"] == "work"


def test_list_events_follows_pagination_across_multiple_pages(tmp_path, mocker):
    service = mocker.Mock()
    service.events.return_value.list.return_value.execute.side_effect = [
        {"items": [{"summary": "First"}], "nextPageToken": "page-2"},
        {"items": [{"summary": "Second"}]},
    ]
    sink = GoogleCalendarSink(service, mocker.Mock(), settings(tmp_path))

    events = sink.list_events(window())

    assert [e["summary"] for e in events] == ["First", "Second"]
    page_tokens = [
        call.kwargs["pageToken"] for call in service.events.return_value.list.call_args_list
    ]
    assert page_tokens == [None, "page-2"]


def test_create_event_inserts_into_the_configured_calendar(tmp_path, mocker):
    service = mocker.Mock()
    sink = GoogleCalendarSink(
        service, mocker.Mock(), settings(tmp_path, CAL_AUTO_CALENDAR_ID="work")
    )
    event = EventDTO(
        summary="A",
        start={"dateTime": "x", "timeZone": "UTC"},
        end={"dateTime": "x", "timeZone": "UTC"},
    )

    sink.create_event(event)

    _, kwargs = service.events.return_value.insert.call_args
    assert kwargs["calendarId"] == "work"


def test_create_todo_inserts_into_the_configured_task_list(tmp_path, mocker):
    service = mocker.Mock()
    sink = GoogleCalendarSink(
        mocker.Mock(), service, settings(tmp_path, CAL_AUTO_TASK_LIST_ID="tasks")
    )
    task = TaskDTO(kind="tasks#task", title="A", notes="", status="needsAction")

    sink.create_todo(task)

    _, kwargs = service.tasks.return_value.insert.call_args
    assert kwargs["tasklist"] == "tasks"


def test_has_scheduled_event_queries_by_private_extended_property(tmp_path, mocker):
    service = mocker.Mock()
    service.events.return_value.list.return_value.execute.return_value = {
        "items": [{"summary": "A"}]
    }
    sink = GoogleCalendarSink(service, mocker.Mock(), settings(tmp_path))

    assert sink.has_scheduled_event("github", "item-1") is True
    _, kwargs = service.events.return_value.list.call_args
    assert kwargs["privateExtendedProperty"] == [
        "source_system=github",
        "source_id=item-1",
    ]


def test_has_scheduled_event_is_false_when_no_event_matches(tmp_path, mocker):
    service = mocker.Mock()
    service.events.return_value.list.return_value.execute.return_value = {"items": []}
    sink = GoogleCalendarSink(service, mocker.Mock(), settings(tmp_path))

    assert sink.has_scheduled_event("github", "item-1") is False


def test_list_scheduled_todo_markers_scans_notes_across_pages(tmp_path, mocker):
    service = mocker.Mock()
    service.tasks.return_value.list.return_value.execute.side_effect = [
        {
            "items": [
                {"notes": f"Event: A {todo_marker('github', 'item-1', 0)}"},
                {"notes": "Event: B, no marker"},
            ],
            "nextPageToken": "page-2",
        },
        {"items": [{"notes": f"Event: C {todo_marker('github', 'item-2', 0)}"}]},
    ]
    sink = GoogleCalendarSink(mocker.Mock(), service, settings(tmp_path))

    markers = sink.list_scheduled_todo_markers()

    assert markers == {
        todo_marker("github", "item-1", 0),
        todo_marker("github", "item-2", 0),
    }


def test_applying_the_same_plan_twice_creates_each_event_and_todo_once(tmp_path, mocker):
    calendar_service = mocker.Mock()
    tasks_service = mocker.Mock()
    created_events: list = []
    created_todos: list = []

    def list_events(**kwargs):
        wanted = set(kwargs.get("privateExtendedProperty") or [])
        matches = [event for event in created_events if wanted.issubset(set(event))]
        return mocker.Mock(execute=lambda: {"items": matches})

    def insert_event(calendarId, body):
        created_events.append(
            [
                f"source_system={body['extendedProperties']['private']['source_system']}",
                f"source_id={body['extendedProperties']['private']['source_id']}",
            ]
        )
        return mocker.Mock(execute=lambda: body)

    def list_tasks(**kwargs):
        return mocker.Mock(execute=lambda: {"items": [{"notes": t.notes} for t in created_todos]})

    def insert_todo(tasklist, body):
        created_todos.append(TaskDTO(**body))
        return mocker.Mock(execute=lambda: body)

    calendar_service.events.return_value.list.side_effect = list_events
    calendar_service.events.return_value.insert.side_effect = insert_event
    tasks_service.tasks.return_value.list.side_effect = list_tasks
    tasks_service.tasks.return_value.insert.side_effect = insert_todo

    sink = GoogleCalendarSink(calendar_service, tasks_service, settings(tmp_path))
    block = ScheduledBlock(
        title="A",
        start=datetime(2024, 1, 1, 9, tzinfo=timezone.utc),
        end=datetime(2024, 1, 1, 11, tzinfo=timezone.utc),
        tasks=["Do X", "Do Y"],
        source="github",
        source_id="item-1",
    )

    def apply_plan():
        existing_markers = sink.list_scheduled_todo_markers()
        if not sink.has_scheduled_event(block.source, block.source_id):
            sink.create_event(build_event(block, settings(tmp_path)))
        for index, todo in enumerate(build_todos(block)):
            marker = todo_marker(block.source, block.source_id, index)
            if marker in existing_markers:
                continue
            sink.create_todo(todo)

    apply_plan()
    apply_plan()

    assert len(created_events) == 1
    assert len(created_todos) == 2
