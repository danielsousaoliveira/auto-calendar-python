from abc import ABC, abstractmethod
from typing import Iterable, List, Optional

from ..dtos.work_item import WorkItem


class TaskSource(ABC):
    @abstractmethod
    def list_work_items(self, statuses: Optional[Iterable[str]] = None) -> List[WorkItem]:
        """Return work items, optionally restricted to the given statuses."""
