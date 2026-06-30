"""Segment altitude from nearby building heights (Phase 1 upgrades in Phase 2)."""

from typing import List

from app.config import CLEARANCE, MIN_ALT
from app.models.mission import CityNode


def compute_altitude(ax: float, ay: float, bx: float, by: float, city_nodes: List[CityNode]) -> float:
    x0, x1 = min(ax, bx) - 30, max(ax, bx) + 30
    y0, y1 = min(ay, by) - 30, max(ay, by) + 30
    max_bh = max(
        (n.building_height for n in city_nodes if x0 <= n.x <= x1 and y0 <= n.y <= y1),
        default=0.0,
    )
    return max(MIN_ALT, max_bh + CLEARANCE)
