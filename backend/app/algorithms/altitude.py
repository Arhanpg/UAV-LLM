"""Phase 1: Corridor-based real-building altitude planner (Section 8.4)."""

import math
from typing import List, Dict, Tuple

def corridor_cruise_altitude(
    ax: float, ay: float, bx: float, by: float,
    buildings: List[Dict],
    corridor_width: float = 15.0,
    safety_margin: float = 15.0,
    max_ceiling: float = 120.0,
    min_alt: float = 30.0
) -> float:
    """
    Finds max building height within the corridor between A and B,
    returns cruise altitude = max(min_alt, max_bh + safety_margin),
    clamped to max_ceiling.
    """
    abx, aby = bx - ax, by - ay
    length = math.hypot(abx, aby)
    
    max_bh = 0.0
    if length > 1e-6:
        dx, dy = abx / length, aby / length
        for b in buildings:
            cx, cy = b['x'], b['y']
            t = ((cx - ax) * dx + (cy - ay) * dy)
            t_clamped = max(0.0, min(length, t))
            px, py = ax + t_clamped * dx, ay + t_clamped * dy
            dist = math.hypot(cx - px, cy - py)
            
            radius = math.hypot(b.get('w', 10), b.get('h', 10)) / 2
            
            if dist < (corridor_width + radius):
                max_bh = max(max_bh, b.get('height', 0.0))
                
    return min(max_ceiling, max(min_alt, max_bh + safety_margin))

def segment_vertical_profile(
    ax: float, ay: float, alt_start: float,
    bx: float, by: float, alt_end: float,
    buildings: List[Dict],
    speed_horizontal: float = 5.0,
    speed_vertical: float = 3.0,
) -> List[Tuple[float, float, float]]:
    """
    Produces a smooth vertical profile for a segment.
    (takeoff climb, cruise at corridor-clearance altitude, controlled descent)
    Returns waypoints [(x, y, z), ...] along the segment.
    """
    cruise_alt = corridor_cruise_altitude(ax, ay, bx, by, buildings)
    
    length_xy = math.hypot(bx - ax, by - ay)
    if length_xy < 1e-6:
        return [(ax, ay, alt_start), (bx, by, alt_end)]
        
    t_climb = max(0, cruise_alt - alt_start) / speed_vertical
    d_climb = t_climb * speed_horizontal
    
    t_descend = max(0, cruise_alt - alt_end) / speed_vertical
    d_descend = t_descend * speed_horizontal
    
    if d_climb + d_descend > length_xy:
        t_half = (length_xy / 2) / speed_horizontal
        max_possible_climb = t_half * speed_vertical
        cruise_alt = min(cruise_alt, max(alt_start, alt_end) + max_possible_climb)
        t_climb = max(0, cruise_alt - alt_start) / speed_vertical
        d_climb = t_climb * speed_horizontal
        t_descend = max(0, cruise_alt - alt_end) / speed_vertical
        d_descend = t_descend * speed_horizontal
        
    waypoints = [(ax, ay, alt_start)]
    
    dx, dy = (bx - ax) / length_xy, (by - ay) / length_xy
    
    if d_climb > 0:
        waypoints.append((ax + dx * d_climb, ay + dy * d_climb, cruise_alt))
        
    if length_xy - d_descend > d_climb:
        waypoints.append((ax + dx * (length_xy - d_descend), ay + dy * (length_xy - d_descend), cruise_alt))
        
    waypoints.append((bx, by, alt_end))
    
    return waypoints
