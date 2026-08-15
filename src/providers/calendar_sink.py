from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Set

from ..dtos.event import EventDTO
from ..dtos.schedule import ScheduleWindow, ScheduledBlock
from ..dtos.task import TaskDTO


class CalendarSink(ABC):
    @abstractmethod
    def list_busy_blocks(self, window: ScheduleWindow) -> List[ScheduledBlock]:
        """Return the blocks already occupying the given window."""

    @abstractmethod
    def create_event(self, event: EventDTO) -> dict:
        """Create a calendar event and return the created resource."""

    @abstractmethod
    def create_todo(self, task: TaskDTO) -> dict:
        """Create a to-do item and return the created resource."""

    @abstractmethod
    def has_scheduled_event(self, source: str, source_id: str, start: datetime) -> bool:
        """Return whether an event for this exact scheduled block already exists."""

    @abstractmethod
    def list_scheduled_todo_markers(self) -> Set[str]:
        """Return the markers of every to-do already created, fetched once per call."""
