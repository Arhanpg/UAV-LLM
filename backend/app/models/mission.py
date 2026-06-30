from dataclasses import dataclass, field
from typing import List


@dataclass
class CityNode:
    idx: int
    lat: float
    lon: float
    x: float
    y: float
    building_height: float
    label: str
    category: str
    description: str = ""
    is_depot: bool = False
    pickups: List[dict] = field(default_factory=list)
    drops: List[dict] = field(default_factory=list)


@dataclass
class GeoZone:
    lat: float
    lon: float
    x: float
    y: float
    radius: float
    kind: str
    label: str = ""
