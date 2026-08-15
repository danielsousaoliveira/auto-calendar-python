from typing import List, Optional, Dict
from dataclasses import dataclass, asdict


@dataclass
class EventDTO:
    summary: str
    start: Dict[str, str]
    end: Dict[str, str]
    description: Optional[str] = None
    location: Optional[str] = None
    colorId: Optional[str] = None
    recurrence: Optional[List[str]] = None
    attendees: Optional[List[Dict[str, str]]] = None
    reminders: Optional[Dict[str, Optional[bool]]] = None

    def to_dict(self) -> Dict:
        filtered_dict = {k: v for k, v in asdict(self).items() if v is not None}
        return filtered_dict
