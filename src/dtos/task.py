from typing import List, Optional, Dict
from dataclasses import dataclass, asdict


@dataclass
class TaskLinkDTO:
    type: str
    description: str
    link: str


@dataclass
class TaskDTO:
    kind: str
    title: str
    notes: str
    status: str
    due: Optional[str] = None
    completed: Optional[str] = None
    deleted: bool = False
    hidden: bool = False
    links: Optional[List[TaskLinkDTO]] = None

    def to_dict(self) -> Dict:
        filtered_dict = {k: v for k, v in asdict(self).items() if v is not None}
        return filtered_dict
