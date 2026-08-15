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
    extendedProperties: Optional[Dict[str, Dict[str, str]]] = None

    def __post_init__(self) -> None:
        if not self.summary:
            raise ValueError("EventDTO requires a non-empty summary")
        if "dateTime" not in self.start or "timeZone" not in self.start:
            raise ValueError("EventDTO.start requires dateTime and timeZone")
        if "dateTime" not in self.end or "timeZone" not in self.end:
            raise ValueError("EventDTO.end requires dateTime and timeZone")

    def to_dict(self) -> Dict:
        filtered_dict = {k: v for k, v in asdict(self).items() if v is not None}
        return filtered_dict
