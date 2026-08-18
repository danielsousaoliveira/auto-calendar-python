from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from src.dtos.event import EventDTO
from src.dtos.schedule import ScheduledBlock, ScheduleWindow
from src.dtos.task import TaskDTO
from src.providers.google_calendar_sink import (
    GoogleCalendarSink,
    block_identity,
    build_event,
    build_todos,
    event_color_id,
    event_matches_block,
    event_to_busy_block,
    event_to_calendar_entry,
    task_to_todo_item,
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


def test_event_to_busy_block_excludes_an_event_ending_exactly_at_window_start(tmp_path):
    event = {
        "summary": "Just before",
        "start": {"dateTime": "2024-01-01T08:00:00+00:00"},
        "end": {"dateTime": "2024-01-01T09:00:00+00:00"},
    }

    assert event_to_busy_block(event, window(), settings(tmp_path)) is None


def test_event_to_busy_block_excludes_an_event_starting_exactly_at_window_end(tmp_path):
    event = {
        "summary": "Just after",
        "start": {"dateTime": "2024-01-01T17:00:00+00:00"},
        "end": {"dateTime": "2024-01-01T18:00:00+00:00"},
    }

    assert event_to_busy_block(event, window(), settings(tmp_path)) is None


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


def test_build_todos_converts_a_non_utc_due_date_to_utc():
    lisbon = ZoneInfo("Europe/Lisbon")
    block = ScheduledBlock(
        title="A",
        start=datetime(2024, 6, 1, 9, tzinfo=lisbon),
        end=datetime(2024, 6, 1, 11, tzinfo=lisbon),
        tasks=["Do X"],
    )

    todos = build_todos(block)

    assert todos[0].due == "2024-06-01T10:00:00Z"


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
        "private": {
            "source_system": "github",
            "source_id": "item-1",
            "auto_calendar_id": block_identity("github", "item-1", block.start),
        }
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


def test_has_scheduled_event_queries_by_a_single_block_identity_property(tmp_path, mocker):
    service = mocker.Mock()
    service.events.return_value.list.return_value.execute.return_value = {
        "items": [{"summary": "A"}]
    }
    sink = GoogleCalendarSink(service, mocker.Mock(), settings(tmp_path))
    start = datetime(2024, 1, 1, 9, tzinfo=timezone.utc)

    assert sink.has_scheduled_event("github", "item-1", start) is True
    _, kwargs = service.events.return_value.list.call_args
    assert kwargs["privateExtendedProperty"] == [
        f"auto_calendar_id={block_identity('github', 'item-1', start)}"
    ]


def test_has_scheduled_event_is_false_when_no_event_matches(tmp_path, mocker):
    service = mocker.Mock()
    service.events.return_value.list.return_value.execute.return_value = {"items": []}
    sink = GoogleCalendarSink(service, mocker.Mock(), settings(tmp_path))

    assert (
        sink.has_scheduled_event("github", "item-1", datetime(2024, 1, 1, 9, tzinfo=timezone.utc))
        is False
    )


def test_has_scheduled_event_does_not_match_a_different_chunk_of_the_same_item(tmp_path, mocker):
    service = mocker.Mock()
    sink = GoogleCalendarSink(service, mocker.Mock(), settings(tmp_path))
    day_one = datetime(2024, 1, 1, 9, tzinfo=timezone.utc)
    day_two = datetime(2024, 1, 2, 9, tzinfo=timezone.utc)

    def list_events(**kwargs):
        wanted = kwargs["privateExtendedProperty"][0]
        matches = (
            [{"summary": "A"}]
            if wanted == f"auto_calendar_id={block_identity('github', 'item-1', day_one)}"
            else []
        )
        return mocker.Mock(execute=lambda: {"items": matches})

    service.events.return_value.list.side_effect = list_events

    assert sink.has_scheduled_event("github", "item-1", day_one) is True
    assert sink.has_scheduled_event("github", "item-1", day_two) is False


def test_find_scheduled_events_queries_by_source_and_source_id(tmp_path, mocker):
    service = mocker.Mock()
    service.events.return_value.list.return_value.execute.return_value = {
        "items": [
            {"id": "evt-2", "start": {"dateTime": "2024-01-02T09:00:00+00:00"}},
            {"id": "evt-1", "start": {"dateTime": "2024-01-01T09:00:00+00:00"}},
        ]
    }
    sink = GoogleCalendarSink(service, mocker.Mock(), settings(tmp_path))

    events = sink.find_scheduled_events("github", "item-1")

    _, kwargs = service.events.return_value.list.call_args
    assert kwargs["privateExtendedProperty"] == [
        "source_system=github",
        "source_id=item-1",
    ]
    assert [event["id"] for event in events] == ["evt-1", "evt-2"]


def test_update_event_calls_the_calendar_api_with_the_event_id(tmp_path, mocker):
    service = mocker.Mock()
    service.events.return_value.update.return_value.execute.return_value = {"id": "evt-1"}
    sink = GoogleCalendarSink(service, mocker.Mock(), settings(tmp_path))
    block = ScheduledBlock(
        title="A",
        start=datetime(2024, 1, 2, 9, tzinfo=timezone.utc),
        end=datetime(2024, 1, 2, 11, tzinfo=timezone.utc),
        source="github",
        source_id="item-1",
    )

    result = sink.update_event("evt-1", build_event(block, settings(tmp_path)))

    assert result == {"id": "evt-1"}
    _, kwargs = service.events.return_value.update.call_args
    assert kwargs["eventId"] == "evt-1"
    assert kwargs["body"]["start"]["dateTime"] == "2024-01-02T09:00:00"


def test_event_matches_block_compares_start_and_end():
    block = ScheduledBlock(
        title="A",
        start=datetime(2024, 1, 1, 9, tzinfo=timezone.utc),
        end=datetime(2024, 1, 1, 11, tzinfo=timezone.utc),
    )
    matching_event = {
        "start": {"dateTime": "2024-01-01T09:00:00+00:00"},
        "end": {"dateTime": "2024-01-01T11:00:00+00:00"},
    }
    moved_event = {
        "start": {"dateTime": "2024-01-01T13:00:00+00:00"},
        "end": {"dateTime": "2024-01-01T15:00:00+00:00"},
    }

    assert event_matches_block(matching_event, block) is True
    assert event_matches_block(moved_event, block) is False


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
        wanted = kwargs["privateExtendedProperty"][0]
        matches = [event for event in created_events if event == wanted]
        return mocker.Mock(execute=lambda: {"items": matches})

    def insert_event(calendarId, body):
        created_events.append(
            f"auto_calendar_id={body['extendedProperties']['private']['auto_calendar_id']}"
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
        if not sink.has_scheduled_event(block.source, block.source_id, block.start):
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


def entries_window():
    return ScheduleWindow(
        start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end=datetime(2024, 1, 2, tzinfo=timezone.utc),
    )


def test_event_to_calendar_entry_converts_a_zero_offset_timed_event(tmp_path):
    event = {
        "summary": "Meeting",
        "start": {"dateTime": "2024-01-01T10:00:00+00:00"},
        "end": {"dateTime": "2024-01-01T11:00:00+00:00"},
    }

    entry = event_to_calendar_entry(event, entries_window(), settings(tmp_path))

    assert entry.title == "Meeting"
    assert entry.start == datetime(2024, 1, 1, 10, tzinfo=timezone.utc)
    assert entry.end == datetime(2024, 1, 1, 11, tzinfo=timezone.utc)
    assert entry.all_day is False


def test_event_to_calendar_entry_converts_a_non_zero_offset_event_into_the_configured_timezone(
    tmp_path,
):
    event = {
        "summary": "Meeting",
        "start": {"dateTime": "2024-01-01T10:00:00+01:00"},
        "end": {"dateTime": "2024-01-01T11:00:00+01:00"},
    }

    entry = event_to_calendar_entry(event, entries_window(), settings(tmp_path))

    assert entry.start == datetime(2024, 1, 1, 9, tzinfo=timezone.utc)
    assert entry.end == datetime(2024, 1, 1, 10, tzinfo=timezone.utc)


def test_event_to_calendar_entry_excludes_a_timed_event_ending_exactly_at_window_start(tmp_path):
    event = {
        "summary": "Just before",
        "start": {"dateTime": "2023-12-31T22:00:00+00:00"},
        "end": {"dateTime": "2024-01-01T00:00:00+00:00"},
    }

    assert event_to_calendar_entry(event, entries_window(), settings(tmp_path)) is None


def test_event_to_calendar_entry_excludes_a_timed_event_starting_exactly_at_window_end(tmp_path):
    event = {
        "summary": "Just after",
        "start": {"dateTime": "2024-01-02T00:00:00+00:00"},
        "end": {"dateTime": "2024-01-02T01:00:00+00:00"},
    }

    assert event_to_calendar_entry(event, entries_window(), settings(tmp_path)) is None


def test_event_to_calendar_entry_includes_all_day_events_by_default(tmp_path):
    event = {"summary": "Holiday", "start": {"date": "2024-01-01"}, "end": {"date": "2024-01-02"}}

    entry = event_to_calendar_entry(event, entries_window(), settings(tmp_path))

    assert entry.title == "Holiday"
    assert entry.all_day is True
    assert entry.start == datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert entry.end == datetime(2024, 1, 2, tzinfo=timezone.utc)


def test_event_to_calendar_entry_excludes_an_all_day_event_starting_on_the_exclusive_window_end(
    tmp_path,
):
    event = {"summary": "Later", "start": {"date": "2024-01-02"}, "end": {"date": "2024-01-03"}}

    assert event_to_calendar_entry(event, entries_window(), settings(tmp_path)) is None


def test_event_to_calendar_entry_excludes_an_all_day_event_ending_exactly_at_window_start(
    tmp_path,
):
    event = {"summary": "Earlier", "start": {"date": "2023-12-31"}, "end": {"date": "2024-01-01"}}

    assert event_to_calendar_entry(event, entries_window(), settings(tmp_path)) is None


def test_event_to_calendar_entry_returns_none_for_a_malformed_all_day_payload(tmp_path):
    event = {"summary": "Broken", "start": {"date": None}, "end": {}}

    assert event_to_calendar_entry(event, entries_window(), settings(tmp_path)) is None


def test_task_to_todo_item_converts_an_outstanding_task():
    task = {"title": "Write report", "status": "needsAction", "notes": "due soon", "due": "x"}

    todo = task_to_todo_item(task)

    assert todo.title == "Write report"
    assert todo.status == "needsAction"
    assert todo.notes == "due soon"
    assert todo.due == "x"


def test_task_to_todo_item_excludes_completed_tasks():
    task = {"title": "Done already", "status": "completed"}

    assert task_to_todo_item(task) is None


def test_task_to_todo_item_excludes_tasks_without_a_title():
    task = {"status": "needsAction"}

    assert task_to_todo_item(task) is None


def test_list_entries_returns_entries_sorted_by_start_across_pages(tmp_path, mocker):
    service = mocker.Mock()
    service.events.return_value.list.return_value.execute.side_effect = [
        {
            "items": [
                {
                    "summary": "Second",
                    "start": {"dateTime": "2024-01-01T12:00:00+00:00"},
                    "end": {"dateTime": "2024-01-01T13:00:00+00:00"},
                }
            ],
            "nextPageToken": "page-2",
        },
        {
            "items": [
                {
                    "summary": "First",
                    "start": {"dateTime": "2024-01-01T09:00:00+00:00"},
                    "end": {"dateTime": "2024-01-01T10:00:00+00:00"},
                }
            ]
        },
    ]
    sink = GoogleCalendarSink(service, mocker.Mock(), settings(tmp_path))

    entries = sink.list_entries(entries_window())

    assert [e.title for e in entries] == ["First", "Second"]


def test_list_outstanding_todos_filters_completed_tasks_across_pages(tmp_path, mocker):
    service = mocker.Mock()
    service.tasks.return_value.list.return_value.execute.side_effect = [
        {
            "items": [
                {"title": "Open task", "status": "needsAction"},
                {"title": "Done task", "status": "completed"},
            ],
            "nextPageToken": "page-2",
        },
        {"items": [{"title": "Another open task", "status": "needsAction"}]},
    ]
    sink = GoogleCalendarSink(mocker.Mock(), service, settings(tmp_path))

    todos = sink.list_outstanding_todos()

    assert [t.title for t in todos] == ["Open task", "Another open task"]
    _, kwargs = service.tasks.return_value.list.call_args_list[0]
    assert kwargs["tasklist"] == "@default"
    assert kwargs["showCompleted"] is False
