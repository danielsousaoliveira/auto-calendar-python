from abc import ABC, abstractmethod
from typing import List, Optional

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
    def find_existing_event(self, title: str, window: ScheduleWindow) -> Optional[dict]:
        """Look up a previously created event with the given title in the window, if any."""
