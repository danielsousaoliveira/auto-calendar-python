from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class CalendarEntryDTO:
    title: str
    start: datetime
    end: datetime
    all_day: bool = False


@dataclass(frozen=True)
class TodoItemDTO:
    title: str
    status: str
    notes: Optional[str] = None
    due: Optional[str] = None
