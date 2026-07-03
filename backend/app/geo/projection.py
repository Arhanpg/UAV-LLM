"""Lat/lon projection and distance helpers."""

import math

from app.config import EARTH_R


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(a))


def lat_lon_to_xy(lat: float, lon: float, origin_lat: float, origin_lon: float) -> tuple[float, float]:
    x = math.radians(lon - origin_lon) * math.cos(math.radians(origin_lat)) * EARTH_R
    y = math.radians(lat - origin_lat) * EARTH_R
    return x, y


def dist_2d(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(ax - bx, ay - by)


def point_segment_dist(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    """Shortest distance from point (px,py) to segment [(ax,ay),(bx,by)]."""
    abx, aby = bx - ax, by - ay
    denom = abx * abx + aby * aby
    if denom < 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * abx + (py - ay) * aby) / denom))
    return math.hypot(px - (ax + t * abx), py - (ay + t * aby))
