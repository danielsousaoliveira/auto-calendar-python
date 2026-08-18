from abc import ABC, abstractmethod
from typing import List, Set

from ..dtos.calendar_entry import CalendarEntryDTO, TodoItemDTO
from ..dtos.event import EventDTO
from ..dtos.schedule import ScheduleWindow, ScheduledBlock
from ..dtos.task import TaskDTO


class CalendarSink(ABC):
    @abstractmethod
    def list_busy_blocks(self, window: ScheduleWindow) -> List[ScheduledBlock]:
        """Return the blocks already occupying the given window."""

    @abstractmethod
    def list_entries(self, window: ScheduleWindow) -> List[CalendarEntryDTO]:
        """Return every calendar entry within the given window."""

    @abstractmethod
    def list_outstanding_todos(self) -> List[TodoItemDTO]:
        """Return to-do items that have not been completed."""

    @abstractmethod
    def create_event(self, event: EventDTO) -> dict:
        """Create a calendar event and return the created resource."""

    @abstractmethod
    def create_todo(self, task: TaskDTO) -> dict:
        """Create a to-do item and return the created resource."""

    @abstractmethod
    def find_scheduled_events(self, source: str, source_id: str) -> List[dict]:
        """Return every managed event for this work item, sorted by start time."""

    @abstractmethod
    def update_event(self, event_id: str, event: EventDTO) -> dict:
        """Update an existing calendar event and return the updated resource."""

    @abstractmethod
    def list_scheduled_todo_markers(self) -> Set[str]:
        """Return the markers of every to-do already created, fetched once per call."""
