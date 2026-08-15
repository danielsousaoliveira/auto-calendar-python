from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from .work_item import Priority, Size, WorkItem


@dataclass(frozen=True)
class ScheduleWindow:
    start: datetime
    end: datetime


@dataclass
class ScheduledBlock:
    title: str
    start: datetime
    end: datetime
    priority: Optional[Priority] = None
    size: Optional[Size] = None
    estimate: Optional[float] = None
    status: Optional[str] = None
    description: Optional[str] = None
    tasks: Optional[List[str]] = None


@dataclass(frozen=True)
class UnscheduledItem:
    work_item: WorkItem
    reason: str


@dataclass(frozen=True)
class SchedulePlan:
    scheduled: List[ScheduledBlock]
    unscheduled: List[UnscheduledItem]
    window: ScheduleWindow

    @property
    def scheduled_blocks(self) -> List[ScheduledBlock]:
        return self.scheduled

    @property
    def unscheduled_items(self) -> List[UnscheduledItem]:
        return self.unscheduled
