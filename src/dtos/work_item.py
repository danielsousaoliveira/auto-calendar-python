from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from typing import Dict, List, Optional


class Priority(IntEnum):
    P0 = 0
    P1 = 1
    P2 = 2
    P3 = 3
    P4 = 4


class Size(IntEnum):
    XL = 0
    L = 1
    M = 2
    S = 3
    XS = 4


SIZE_DEFAULT_ESTIMATE_HOURS: Dict[Size, float] = {
    Size.XL: 8.0,
    Size.L: 6.0,
    Size.M: 4.0,
    Size.S: 2.0,
    Size.XS: 1.0,
}


@dataclass
class WorkItem:
    id: Optional[str] = None
    title: Optional[str] = None
    assignee: Optional[str] = None
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    priority: Optional[Priority] = None
    status: Optional[str] = None
    size: Optional[Size] = None
    estimate: Optional[float] = None
    description: Optional[str] = None
    tasks: Optional[List[str]] = None
