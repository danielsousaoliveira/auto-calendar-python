"""End-to-end sync operation: fetch, plan, and (optionally) apply to the calendar."""

from __future__ import annotations

from dataclasses import dataclass, field

from .dtos.schedule import ScheduleWindow, ScheduledBlock, SchedulePlan, UnscheduledItem
from .providers.calendar_sink import CalendarSink
from .providers.google_calendar_sink import (
    build_event,
    build_todos,
    event_matches_block,
    todo_marker,
)
from .providers.task_source import TaskSource
from .scheduler import schedule
from .settings import Settings


@dataclass(frozen=True)
class SyncResult:
    plan: SchedulePlan
    created: list[ScheduledBlock] = field(default_factory=list)
    updated: list[ScheduledBlock] = field(default_factory=list)
    skipped: list[ScheduledBlock] = field(default_factory=list)
    unscheduled: list[UnscheduledItem] = field(default_factory=list)
    applied: bool = False

    @property
    def scheduled(self) -> list[ScheduledBlock]:
        return self.plan.scheduled


def run_sync(
    task_source: TaskSource,
    calendar_sink: CalendarSink,
    window: ScheduleWindow,
    settings: Settings,
    apply: bool = False,
) -> SyncResult:
    work_items = task_source.list_work_items(settings.schedulable_statuses)
    busy_blocks = calendar_sink.list_busy_blocks(window)

    work_item_keys = {(item.source, item.id) for item in work_items}
    external_busy_blocks = [
        block
        for block in busy_blocks
        if not (
            block.source and block.source_id and (block.source, block.source_id) in work_item_keys
        )
    ]

    plan = schedule(work_items, external_busy_blocks, window)

    created: list[ScheduledBlock] = []
    updated: list[ScheduledBlock] = []
    skipped: list[ScheduledBlock] = []

    if not apply:
        return SyncResult(plan=plan, created=created, skipped=skipped, unscheduled=plan.unscheduled)

    existing_todo_markers = calendar_sink.list_scheduled_todo_markers()
    existing_events_by_item: dict[tuple[str, str], list[dict]] = {}
    consumed_by_item: dict[tuple[str, str], int] = {}

    for task in plan.scheduled:
        existing_event = None
        if task.source and task.source_id:
            key = (task.source, task.source_id)
            if key not in existing_events_by_item:
                existing_events_by_item[key] = calendar_sink.find_scheduled_events(*key)
            matches = existing_events_by_item[key]
            index = consumed_by_item.get(key, 0)
            if index < len(matches):
                consumed_by_item[key] = index + 1
                existing_event = matches[index]

        if existing_event is None:
            calendar_sink.create_event(build_event(task, settings))
            created.append(task)
        elif event_matches_block(existing_event, task):
            skipped.append(task)
        else:
            calendar_sink.update_event(existing_event["id"], build_event(task, settings))
            updated.append(task)

        for index, todo in enumerate(build_todos(task)):
            marker = todo_marker(task.source, task.source_id, index)
            if marker and marker in existing_todo_markers:
                continue
            calendar_sink.create_todo(todo)
            if marker:
                existing_todo_markers.add(marker)

    return SyncResult(
        plan=plan,
        created=created,
        updated=updated,
        skipped=skipped,
        unscheduled=plan.unscheduled,
        applied=True,
    )
