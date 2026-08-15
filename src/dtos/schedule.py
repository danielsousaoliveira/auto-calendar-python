from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from .work_item import Priority, Size


@dataclass
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


SchedulePlan = List[ScheduledBlock]
