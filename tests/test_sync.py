from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from src.dtos.schedule import ScheduleWindow, ScheduledBlock
from src.dtos.work_item import Priority, Size, WorkItem
from src.providers.calendar_sink import CalendarSink
from src.providers.task_source import TaskSource
from src.settings import load_settings
from src.sync import run_sync

TZ = ZoneInfo("Europe/Lisbon")


class StubTaskSource(TaskSource):
    def __init__(self, items):
        self.items = items

    def list_work_items(self, statuses=None):
        if statuses is None:
            return self.items
        wanted = set(statuses)
        return [item for item in self.items if item.status in wanted]


class StubCalendarSink(CalendarSink):
    def __init__(self, busy_blocks=None, todo_markers=None, scheduled_events=None):
        self.busy_blocks = busy_blocks or []
        self.todo_markers = set(todo_markers or set())
        self.scheduled_events = scheduled_events or {}
        self.created_events = []
        self.created_todos = []
        self.updated_events = []

    def list_busy_blocks(self, window):
        return self.busy_blocks

    def list_entries(self, window):
        return []

    def list_outstanding_todos(self):
        return []

    def create_event(self, event):
        self.created_events.append(event)
        return {}

    def create_todo(self, task):
        self.created_todos.append(task)
        return {}

    def find_scheduled_events(self, source, source_id):
        return self.scheduled_events.get((source, source_id), [])

    def update_event(self, event_id, event):
        self.updated_events.append((event_id, event))
        return {"id": event_id}

    def list_scheduled_todo_markers(self):
        return self.todo_markers


def _settings():
    return load_settings(
        {
            "CAL_AUTO_TIMEZONE": "Europe/Lisbon",
            "GITHUB_TOKEN": "token",
            "GITHUB_PROJECT_ID": "project",
        }
    )


def _window():
    return ScheduleWindow(
        start=datetime(2026, 8, 17, 9, 0, tzinfo=TZ),
        end=datetime(2026, 8, 17, 17, 0, tzinfo=TZ),
    )


def _work_item(item_id, title):
    return WorkItem(
        id=item_id,
        source="github",
        title=title,
        priority=Priority.P1,
        size=Size.S,
        status="Backlog",
        tasks=["do the thing"],
    )


def _existing_event(event_id, start, end):
    return {
        "id": event_id,
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
    }


def test_dry_run_plans_without_writing():
    task_source = StubTaskSource([_work_item("1", "Write docs")])
    calendar_sink = StubCalendarSink()

    result = run_sync(task_source, calendar_sink, _window(), _settings(), apply=False)

    assert not result.applied
    assert len(result.plan.scheduled) == 1
    assert result.created == []
    assert result.skipped == []
    assert calendar_sink.created_events == []
    assert calendar_sink.created_todos == []


def test_apply_creates_new_items_and_skips_existing():
    task_source = StubTaskSource([_work_item("1", "Write docs"), _work_item("2", "Ship it")])
    calendar_sink = StubCalendarSink()

    dry_run = run_sync(task_source, calendar_sink, _window(), _settings(), apply=False)
    already_scheduled_block = dry_run.plan.scheduled[0]
    calendar_sink.scheduled_events = {
        (already_scheduled_block.source, already_scheduled_block.source_id): [
            _existing_event(
                "existing-1", already_scheduled_block.start, already_scheduled_block.end
            )
        ]
    }

    result = run_sync(task_source, calendar_sink, _window(), _settings(), apply=True)

    assert result.applied
    assert len(result.created) == 1
    assert len(result.updated) == 0
    assert len(result.skipped) == 1
    assert len(calendar_sink.created_events) == 1
    assert len(calendar_sink.created_todos) == 2


def test_apply_skips_existing_event_that_still_matches_the_plan():
    item = _work_item("1", "Write docs")
    start = datetime(2026, 8, 17, 9, tzinfo=TZ)
    end = datetime(2026, 8, 17, 11, tzinfo=TZ)
    existing = StubCalendarSink(
        busy_blocks=[
            ScheduledBlock(title=item.title, start=start, end=end, source="github", source_id="1")
        ],
        scheduled_events={("github", "1"): [_existing_event("existing-1", start, end)]},
    )

    result = run_sync(StubTaskSource([item]), existing, _window(), _settings(), apply=True)

    assert result.created == []
    assert result.updated == []
    assert len(result.skipped) == 1
    assert existing.created_events == []
    assert existing.updated_events == []


def test_apply_moves_existing_event_when_the_plan_reschedules_it():
    urgent_item = _work_item("1", "Fix outage")
    already_scheduled_item = replace(_work_item("2", "Write docs"), priority=Priority.P2)
    start = datetime(2026, 8, 17, 9, tzinfo=TZ)
    end = datetime(2026, 8, 17, 11, tzinfo=TZ)
    existing = StubCalendarSink(
        busy_blocks=[
            ScheduledBlock(
                title=already_scheduled_item.title,
                start=start,
                end=end,
                source="github",
                source_id="2",
            )
        ],
        scheduled_events={("github", "2"): [_existing_event("existing-2", start, end)]},
    )

    result = run_sync(
        StubTaskSource([urgent_item, already_scheduled_item]),
        existing,
        _window(),
        _settings(),
        apply=True,
    )

    assert len(result.created) == 1
    assert len(result.updated) == 1
    assert result.updated[0].source_id == "2"
    assert len(existing.created_events) == 1
    assert existing.created_events[0].extendedProperties["private"]["source_id"] == "1"
    assert len(existing.updated_events) == 1
    updated_event_id, updated_event = existing.updated_events[0]
    assert updated_event_id == "existing-2"
    assert updated_event.start["dateTime"] != start.strftime("%Y-%m-%dT%H:%M:%S")


def test_unscheduled_items_are_reported():
    huge_item = replace(_work_item("1", "Too big"), size=Size.XL, estimate=100.0)
    task_source = StubTaskSource([huge_item])
    calendar_sink = StubCalendarSink()

    result = run_sync(task_source, calendar_sink, _window(), _settings(), apply=False)

    assert result.plan.scheduled != []
    assert len(result.unscheduled) == 1
    assert result.unscheduled[0].work_item is huge_item
