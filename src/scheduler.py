from datetime import datetime, timedelta

from .dtos.schedule import ScheduleWindow, ScheduledBlock, SchedulePlan, UnscheduledItem
from .dtos.work_item import Priority, Size, WorkItem, SIZE_DEFAULT_ESTIMATE_HOURS
from .errors import SchedulingError


def schedule(
    work_items: list[WorkItem],
    busy_blocks: list[ScheduledBlock],
    window: ScheduleWindow,
) -> SchedulePlan:
    if window.start.tzinfo is None or window.end.tzinfo is None or window.start >= window.end:
        raise SchedulingError(
            "Invalid schedule window", "Provide an aware window with start before end."
        )
    items = sorted(
        work_items,
        key=lambda item: (
            item.priority if item.priority is not None else Priority.P4,
            item.size.value if item.size is not None else float("inf"),
        ),
    )
    scheduled: list[ScheduledBlock] = []
    unscheduled: list[UnscheduledItem] = []
    occupied = _merge_blocks(busy_blocks)
    remaining = {_key(item): _estimate(item) for item in items}
    day = window.start.date()
    last_day = window.end.date()

    while day <= last_day and items:
        day_start = datetime.combine(day, window.start.timetz())
        day_end = datetime.combine(day, window.end.timetz())
        if day == window.start.date():
            day_start = window.start
        if day == last_day:
            day_end = window.end
        day_window = ScheduleWindow(day_start, day_end)
        large_scheduled = False
        continuing_item = None

        while items:
            item = items[0]
            if item is not continuing_item and item.size in (Size.L, Size.XL) and large_scheduled:
                smaller = next(
                    (
                        i
                        for i, value in enumerate(items[1:], 1)
                        if value.size not in (Size.L, Size.XL)
                    ),
                    None,
                )
                if smaller is None:
                    break
                items.insert(0, items.pop(smaller))
                item = items[0]
            if item.size in (Size.L, Size.XL):
                large_scheduled = True

            estimate = remaining[_key(item)]
            start, end = _next_slot(day_window, timedelta(hours=estimate), occupied)
            if start is None or end is None:
                break
            duration = (end - start).total_seconds() / 3600
            scheduled_block = ScheduledBlock(
                title=item.title or "",
                start=start,
                end=end,
                priority=item.priority,
                size=item.size,
                estimate=estimate,
                status=item.status,
                description=item.description,
                tasks=item.tasks,
                source=item.source,
                source_id=item.id,
            )
            scheduled.append(scheduled_block)
            occupied.append(scheduled_block)
            occupied.sort(key=lambda block: block.start)
            if estimate > duration:
                remaining[_key(item)] = estimate - duration
                continuing_item = item
                continue
            items.pop(0)
            continuing_item = None
        day += timedelta(days=1)

    unscheduled.extend(
        UnscheduledItem(item, "No available time remains in the scheduling window")
        for item in items
    )
    return SchedulePlan(scheduled, unscheduled, window)


def _key(item: WorkItem) -> int:
    return id(item)


def _estimate(item: WorkItem) -> float:
    if item.estimate is not None:
        return item.estimate
    if item.size is not None:
        return SIZE_DEFAULT_ESTIMATE_HOURS[item.size]
    return 1.0


def _next_slot(window: ScheduleWindow, duration: timedelta, blocks: list[ScheduledBlock]):
    current = window.start
    for block in blocks:
        if block.end <= window.start or block.start >= window.end:
            continue
        start = max(current, window.start)
        block_start = max(block.start.astimezone(window.start.tzinfo), window.start)
        if start + duration <= block_start:
            return start, start + duration
        if start < block_start:
            return start, block_start
        current = max(current, block.end.astimezone(window.start.tzinfo))
    if current + duration <= window.end:
        return current, current + duration
    if current < window.end:
        return current, window.end
    return None, None


def _merge_blocks(blocks: list[ScheduledBlock]) -> list[ScheduledBlock]:
    merged: list[ScheduledBlock] = []
    for block in sorted(blocks, key=lambda item: item.start):
        if merged and block.start <= merged[-1].end:
            previous = merged[-1]
            merged[-1] = ScheduledBlock(
                previous.title, previous.start, max(previous.end, block.end)
            )
        else:
            merged.append(block)
    return merged
