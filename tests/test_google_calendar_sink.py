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


def test_find_existing_event_matches_by_title_in_window(tmp_path, mocker):
    service = mocker.Mock()
    service.events.return_value.list.return_value.execute.return_value = {
        "items": [
            {
                "summary": "A",
                "start": {"dateTime": "2024-01-01T10:00:00+00:00"},
                "end": {"dateTime": "2024-01-01T11:00:00+00:00"},
            }
        ]
    }
    sink = GoogleCalendarSink(service, mocker.Mock(), settings(tmp_path))

    assert sink.find_existing_event("A", window()) is not None
    assert sink.find_existing_event("B", window()) is None
