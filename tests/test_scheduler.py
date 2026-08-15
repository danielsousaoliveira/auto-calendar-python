from datetime import datetime

import pytest

from src.dtos.schedule import ScheduledBlock, ScheduleWindow
from src.dtos.work_item import Priority, Size, WorkItem
from src.errors import SchedulingError
from src.scheduler import schedule


def backlog(title, size="S", estimate=2, priority="P1", id=None):
    return WorkItem(
        id=id,
        title=title,
        size=Size[size],
        estimate=estimate,
        priority=Priority[priority],
        status="Backlog",
    )


def busy(summary, start, end):
    return ScheduledBlock(
        title=summary,
        start=datetime.fromisoformat(start),
        end=datetime.fromisoformat(end),
    )


def window(start_date="2024-01-01", end_date="2024-01-01", start_hour="09:00", end_hour="17:00"):
    return ScheduleWindow(
        start=datetime.fromisoformat(f"{start_date}T{start_hour}:00+00:00"),
        end=datetime.fromisoformat(f"{end_date}T{end_hour}:00+00:00"),
    )


def placements(blocks):
    return [(block.title, block.start.isoformat(), block.end.isoformat()) for block in blocks]


def test_scheduler_leaves_empty_backlog_empty():
    assert schedule([], [], window()).scheduled == []


def test_scheduler_places_single_item_that_fits():
    result = schedule([backlog("A", estimate=2)], [], window())

    assert placements(result.scheduled) == [
        ("A", "2024-01-01T09:00:00+00:00", "2024-01-01T11:00:00+00:00")
    ]


def test_scheduler_splits_item_around_existing_commitment():
    result = schedule(
        [backlog("A", estimate=6)],
        [busy("Meeting", "2024-01-01T11:00:00+00:00", "2024-01-01T13:00:00+00:00")],
        window(),
    )

    assert placements(result.scheduled) == [
        ("A", "2024-01-01T09:00:00+00:00", "2024-01-01T11:00:00+00:00"),
        ("A", "2024-01-01T13:00:00+00:00", "2024-01-01T17:00:00+00:00"),
    ]


def test_scheduler_uses_size_when_estimate_is_missing():
    result = schedule([backlog("A", "M", None)], [], window())

    assert placements(result.scheduled) == [
        ("A", "2024-01-01T09:00:00+00:00", "2024-01-01T13:00:00+00:00")
    ]


def test_scheduler_rolls_over_an_item_across_days():
    result = schedule([backlog("A", estimate=10)], [], window(end_date="2024-01-02"))

    assert placements(result.scheduled) == [
        ("A", "2024-01-01T09:00:00+00:00", "2024-01-01T17:00:00+00:00"),
        ("A", "2024-01-02T09:00:00+00:00", "2024-01-02T11:00:00+00:00"),
    ]


def test_scheduler_reports_unscheduled_work_when_the_window_cannot_fit_it():
    result = schedule([backlog("A", estimate=9)], [], window())

    assert placements(result.scheduled) == [
        ("A", "2024-01-01T09:00:00+00:00", "2024-01-01T17:00:00+00:00")
    ]
    assert [item.work_item.title for item in result.unscheduled] == ["A"]


def test_scheduler_populates_source_id_from_the_work_item():
    result = schedule([backlog("A", id="item-1")], [], window())

    assert [block.source_id for block in result.scheduled] == ["item-1"]


def test_scheduler_preserves_offset_event_clock_as_utc():
    result = schedule(
        [backlog("A", estimate=2)],
        [busy("Meeting", "2024-01-01T10:00:00+01:00", "2024-01-01T12:00:00+01:00")],
        window(),
    )

    assert placements(result.scheduled) == [
        ("A", "2024-01-01T11:00:00+00:00", "2024-01-01T13:00:00+00:00")
    ]


def test_scheduler_raises_scheduling_error_on_a_naive_window():
    with pytest.raises(SchedulingError, match="Invalid schedule window"):
        schedule(
            [],
            [],
            ScheduleWindow(start=datetime(2024, 1, 1, 9), end=datetime(2024, 1, 1, 17)),
        )
