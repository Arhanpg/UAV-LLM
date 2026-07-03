"""Corridor-based 3D altitude planning (Phase 2, spec §8.4).

For each flight segment the planner buffers the straight-line path by a corridor
half-width, finds the tallest real building footprint intersecting that corridor,
and sets cruise altitude = tallest + safety margin, clamped to the operational
ceiling. A route-level pass then builds a *smooth, rate-limited* vertical profile
(takeoff climb → cruise → controlled descent) so the 3D animation never teleports
the drone in z.
"""

from __future__ import annotations

from typing import List, Optional

from app.config import (
    ALT_SAFETY_MARGIN,
    CORRIDOR_WIDTH,
    MAX_CEILING,
    MIN_ALT,
    VERTICAL_SPEED,
)
from app.geo.buildings import BuildingIndex
from app.geo.projection import dist_2d


def corridor_cruise_altitude(
    ax: float,
    ay: float,
    bx: float,
    by: float,
    bindex: Optional[BuildingIndex],
    corridor_width: float = CORRIDOR_WIDTH,
    margin: float = ALT_SAFETY_MARGIN,
    ceiling: float = MAX_CEILING,
) -> float:
    """Cruise altitude for one segment: clear the tallest building in the corridor."""
    tallest = 0.0
    if bindex is not None:
        tallest = bindex.max_height_in_corridor(ax, ay, bx, by, corridor_width / 2.0)
    return min(ceiling, max(MIN_ALT, tallest + margin))


# Backward-compatible helper used by the flight-path builder.
def compute_altitude(ax, ay, bx, by, city_nodes=None, bindex=None) -> float:
    """Segment cruise altitude. Prefers the corridor building index; falls back
    to nearby city-node building heights when no index is supplied."""
    if bindex is not None:
        return corridor_cruise_altitude(ax, ay, bx, by, bindex)
    tallest = 0.0
    if city_nodes:
        x0, x1 = min(ax, bx) - 30, max(ax, bx) + 30
        y0, y1 = min(ay, by) - 30, max(ay, by) + 30
        tallest = max(
            (n.building_height for n in city_nodes if x0 <= n.x <= x1 and y0 <= n.y <= y1),
            default=0.0,
        )
    return min(MAX_CEILING, max(MIN_ALT, tallest + ALT_SAFETY_MARGIN))


def rate_limited_profile(
    waypoints_xy: List[tuple],
    cruise_alts: List[float],
    vspeed: float = VERTICAL_SPEED,
    speed: float = None,
    samples_per_seg: int = 12,
) -> List[dict]:
    """Densely sample the route in 3D with a rate-limited vertical channel.

    ``waypoints_xy[k]`` is the (x,y) of node k; ``cruise_alts[k]`` (k>=1) is the
    cruise altitude for the segment arriving at node k. Vertical rate is capped at
    ``vspeed`` (m/s) given the horizontal cruise ``speed`` (m/s), so climbs and
    descents are gradual rather than instantaneous.
    """
    from app.config import UAV_SPEED

    speed = speed or UAV_SPEED
    profile: List[dict] = []
    z = MIN_ALT
    profile.append({"x": waypoints_xy[0][0], "y": waypoints_xy[0][1], "z": z, "seg": 0})
    for k in range(1, len(waypoints_xy)):
        ax, ay = waypoints_xy[k - 1]
        bx, by = waypoints_xy[k]
        target = cruise_alts[k]
        seg_len = max(1e-6, dist_2d(ax, ay, bx, by))
        # max altitude change achievable over this segment at the vertical limit
        max_dz = vspeed * (seg_len / speed)
        for s in range(1, samples_per_seg + 1):
            frac = s / samples_per_seg
            x = ax + (bx - ax) * frac
            y = ay + (by - ay) * frac
            allowed = max_dz * frac
            # climb toward target early, hold cruise, then it becomes the new z
            desired = target
            dz = max(-allowed, min(allowed, desired - z))
            zc = z + dz
            profile.append({"x": x, "y": y, "z": round(zc, 2), "seg": k})
        z = profile[-1]["z"]
    return profile
