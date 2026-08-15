from typing import Optional
from dataclasses import dataclass


@dataclass
class ProjectItemDTO:
    id: Optional[str] = None
    title: Optional[str] = None
    assignee: Optional[str] = None
    startDate: Optional[str] = None
    endDate: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    size: Optional[str] = None
    estimate: Optional[float] = None
    description: Optional[str] = None
    tasks: Optional[list[str]] = None

    def display(self):
        print(f"Item ID: {self.id}")
        print(f"Title: {self.title}")
        print(f"Assignee: {self.assignee}")
        print(f"Start date: {self.startDate}")
        print(f"End date: {self.endDate}")
        print(f"Priority: {self.priority}")
        print(f"Status: {self.status}")
        print(f"Size: {self.size}")
        print(f"Estimate: {self.estimate}")
        print(f"Description: {self.description}")
        print(f"Tasks: {self.tasks}")
