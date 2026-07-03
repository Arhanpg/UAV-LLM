"""Load committed OSM building footprints and index them for corridor queries.

Footprints are stored in lat/lon (GeoJSON). For altitude planning we project
each footprint to the same local ENU metre frame used by the city (origin =
depot), reduce it to a centroid + bounding radius + height, and answer
"tallest building whose footprint intersects this flight corridor" queries.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import List

from app.config import BUILDINGS_PATH
from app.geo.projection import lat_lon_to_xy, point_segment_dist


@dataclass
class Footprint:
    cx: float       # centroid x (m)
    cy: float       # centroid y (m)
    radius: float   # bounding radius (m) from centroid to farthest ring vertex
    height: float   # building height (m)
    name: str = ""


class BuildingIndex:
    """Projected footprints + corridor intersection queries."""

    def __init__(self, footprints: List[Footprint]):
        self.footprints = footprints

    def max_height_in_corridor(self, ax, ay, bx, by, half_width: float) -> float:
        """Tallest building whose footprint intersects the buffered segment."""
        best = 0.0
        for fp in self.footprints:
            if point_segment_dist(fp.cx, fp.cy, ax, ay, bx, by) <= half_width + fp.radius:
                best = max(best, fp.height)
        return best

    def buildings_near(self, ax, ay, bx, by, half_width: float) -> List[Footprint]:
        return [
            fp
            for fp in self.footprints
            if point_segment_dist(fp.cx, fp.cy, ax, ay, bx, by) <= half_width + fp.radius
        ]

    def __len__(self) -> int:
        return len(self.footprints)


def _raw_features() -> list:
    if not BUILDINGS_PATH.exists():
        return []
    with open(BUILDINGS_PATH, encoding="utf-8") as f:
        return json.load(f).get("features", [])


@lru_cache(maxsize=8)
def load_building_index(origin_lat: float, origin_lon: float) -> BuildingIndex:
    """Project the committed GeoJSON into the city's local metre frame (cached)."""
    footprints: List[Footprint] = []
    for feat in _raw_features():
        geom = feat.get("geometry", {})
        if geom.get("type") != "Polygon":
            continue
        ring = geom["coordinates"][0]
        pts = [lat_lon_to_xy(lat, lon, origin_lat, origin_lon) for lon, lat in ring]
        if len(pts) < 3:
            continue
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        radius = max(((px - cx) ** 2 + (py - cy) ** 2) ** 0.5 for px, py in pts)
        props = feat.get("properties", {})
        footprints.append(
            Footprint(cx, cy, radius, float(props.get("height", 9.0)), props.get("name", ""))
        )
    return BuildingIndex(footprints)


def buildings_geojson() -> dict:
    """Raw committed GeoJSON for the frontend to extrude (served by /api/buildings)."""
    if not BUILDINGS_PATH.exists():
        return {"type": "FeatureCollection", "features": []}
    with open(BUILDINGS_PATH, encoding="utf-8") as f:
        return json.load(f)
