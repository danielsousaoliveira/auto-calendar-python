"""End-to-end sync operation: fetch, plan, and (optionally) apply to the calendar."""

from __future__ import annotations

from dataclasses import dataclass, field

from .dtos.schedule import ScheduleWindow, ScheduledBlock, SchedulePlan, UnscheduledItem
from .providers.calendar_sink import CalendarSink
from .providers.google_calendar_sink import build_event, build_todos, todo_marker
from .providers.task_source import TaskSource
from .scheduler import schedule
from .settings import Settings


@dataclass(frozen=True)
class SyncResult:
    plan: SchedulePlan
    created: list[ScheduledBlock] = field(default_factory=list)
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

    scheduled_items = {
        (block.source, block.source_id) for block in busy_blocks if block.source and block.source_id
    }
    scheduled_blocks: dict[tuple[str | None, str | None], ScheduledBlock] = {
        (block.source, block.source_id): block
        for block in busy_blocks
        if block.source and block.source_id
    }
    skipped = [
        scheduled_blocks[(item.source, item.id)]
        for item in work_items
        if (item.source, item.id) in scheduled_items
    ]
    work_items = [item for item in work_items if (item.source, item.id) not in scheduled_items]

    plan = schedule(work_items, busy_blocks, window)

    created: list[ScheduledBlock] = []

    if not apply:
        return SyncResult(plan=plan, created=created, skipped=skipped, unscheduled=plan.unscheduled)

    existing_todo_markers = calendar_sink.list_scheduled_todo_markers()

    for task in plan.scheduled:
        already_scheduled = (
            task.source
            and task.source_id
            and calendar_sink.has_scheduled_event(task.source, task.source_id, task.start)
        )
        if already_scheduled:
            skipped.append(task)
        else:
            event = build_event(task, settings)
            calendar_sink.create_event(event)
            created.append(task)

        for index, todo in enumerate(build_todos(task)):
            marker = todo_marker(task.source, task.source_id, index)
            if marker and marker in existing_todo_markers:
                continue
            calendar_sink.create_todo(todo)
            if marker:
                existing_todo_markers.add(marker)

    return SyncResult(
        plan=plan, created=created, skipped=skipped, unscheduled=plan.unscheduled, applied=True
    )
