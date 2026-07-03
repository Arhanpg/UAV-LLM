"""Fetch real OSM building footprints for the Dharwad-Hubli catalog (Phase 2).

Queries the Overpass API for `building` ways within a radius of every catalog
location, extracts `height` / `building:levels` tags (defaulting to 3 levels =
9 m where missing), and writes a compact GeoJSON FeatureCollection to
``backend/data/buildings_dharwad.geojson``. The result is committed to the repo
so the app renders real 3D geometry offline, with no live Overpass dependency at
demo time.

Run once:            python -m scripts.fetch_buildings
Force offline gen:   python -m scripts.fetch_buildings --offline

When the Overpass API is unreachable (no network at build time), the script
falls back to a deterministic generator that places realistic building clusters
around each real catalog coordinate using its real recorded height. Those
features are tagged ``source: "generated"``; true OSM features are tagged
``source: "osm"``. Re-run online to replace the generated file with real data.
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import httpx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.geo.locations import load_locations  # noqa: E402

OUT_PATH = Path(__file__).resolve().parents[1] / "data" / "buildings_dharwad.geojson"
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
RADIUS_M = 350          # buildings within this radius of each catalog location
LEVEL_HEIGHT_M = 3.0    # metres per building level
DEFAULT_LEVELS = 3      # OSM default when height/levels missing


def _parse_height(tags: dict) -> float:
    """Best-effort building height in metres from OSM tags."""
    h = tags.get("height")
    if h:
        try:
            return float(str(h).replace("m", "").strip())
        except ValueError:
            pass
    levels = tags.get("building:levels") or tags.get("levels")
    if levels:
        try:
            return max(1.0, float(str(levels).split(";")[0])) * LEVEL_HEIGHT_M
        except ValueError:
            pass
    return DEFAULT_LEVELS * LEVEL_HEIGHT_M


def build_query(locations: list[tuple]) -> str:
    clauses = "\n".join(
        f'  way["building"](around:{RADIUS_M},{lat},{lon});' for _, lat, lon, *_ in locations
    )
    return f"[out:json][timeout:120];\n(\n{clauses}\n);\nout body geom;"


def fetch(query: str) -> dict:
    last_err = None
    for url in OVERPASS_ENDPOINTS:
        for attempt in range(2):
            try:
                print(f"  querying {url} (attempt {attempt + 1})...")
                r = httpx.post(url, data={"data": query}, timeout=180.0)
                if r.status_code == 200:
                    return r.json()
                last_err = f"HTTP {r.status_code}"
            except Exception as e:  # network / timeout / rate limit
                last_err = str(e)
            time.sleep(3)
    raise RuntimeError(f"Overpass fetch failed: {last_err}")


def to_geojson(data: dict) -> dict:
    features = []
    for el in data.get("elements", []):
        if el.get("type") != "way" or "geometry" not in el:
            continue
        coords = [[pt["lon"], pt["lat"]] for pt in el["geometry"]]
        if len(coords) < 3:
            continue
        if coords[0] != coords[-1]:
            coords.append(coords[0])  # close ring
        tags = el.get("tags", {})
        features.append(
            {
                "type": "Feature",
                "id": el["id"],
                "properties": {
                    "height": round(_parse_height(tags), 1),
                    "name": tags.get("name", ""),
                    "building": tags.get("building", "yes"),
                },
                "geometry": {"type": "Polygon", "coordinates": [coords]},
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _rect(clat, clon, w_m, h_m, rot_deg):
    """Axis-rotated rectangle footprint (list of [lon,lat]) around a centre."""
    mlat = 111111.0
    mlon = 111111.0 * math.cos(math.radians(clat))
    a = math.radians(rot_deg)
    ca, sa = math.cos(a), math.sin(a)
    ring = []
    for dx, dy in ((-w_m / 2, -h_m / 2), (w_m / 2, -h_m / 2), (w_m / 2, h_m / 2), (-w_m / 2, h_m / 2)):
        rx, ry = dx * ca - dy * sa, dx * sa + dy * ca
        ring.append([clon + rx / mlon, clat + ry / mlat])
    ring.append(ring[0])
    return ring


def generate_offline(locations: list[tuple]) -> dict:
    """Deterministic building clusters derived from real catalog coordinates.

    Each location gets one anchor building at its recorded height plus a small
    cluster of shorter neighbours, giving the 3D scene genuine geometry tied to
    real GPS coordinates when the live Overpass API is unavailable.
    """
    rng = np.random.default_rng(20260703)
    features = []
    bid = 0
    for name, lat, lon, bh, *_ in locations:
        # Anchor building at the real recorded height.
        features.append(
            {
                "type": "Feature",
                "id": bid,
                "properties": {"height": round(float(bh), 1), "name": name, "building": "yes", "source": "generated"},
                "geometry": {"type": "Polygon", "coordinates": [_rect(lat, lon, 34, 26, rng.uniform(0, 90))]},
            }
        )
        bid += 1
        # Cluster of neighbours within ~180 m.
        for _ in range(int(rng.integers(3, 7))):
            ang = rng.uniform(0, 2 * math.pi)
            r = rng.uniform(35, 180)
            dlat = (r * math.sin(ang)) / 111111.0
            dlon = (r * math.cos(ang)) / (111111.0 * math.cos(math.radians(lat)))
            h = round(float(max(6.0, rng.normal(max(9.0, bh * 0.55), 5.0))), 1)
            features.append(
                {
                    "type": "Feature",
                    "id": bid,
                    "properties": {"height": h, "name": "", "building": "yes", "source": "generated"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            _rect(lat + dlat, lon + dlon, rng.uniform(14, 30), rng.uniform(12, 26), rng.uniform(0, 90))
                        ],
                    },
                }
            )
            bid += 1
    return {"type": "FeatureCollection", "features": features, "generated": True}


def main() -> int:
    offline = "--offline" in sys.argv
    locations = load_locations()
    gj = None
    if not offline:
        print(f"Fetching OSM buildings around {len(locations)} Dharwad-Hubli locations...")
        try:
            data = fetch(build_query(locations))
            gj = to_geojson(data)
            for f in gj["features"]:
                f["properties"]["source"] = "osm"
            print(f"Fetched {len(gj['features'])} real OSM footprints.")
        except RuntimeError as e:
            print(f"[warn] {e}\n[warn] falling back to deterministic offline generator.")
    if gj is None or not gj["features"]:
        gj = generate_offline(locations)
        print(f"Generated {len(gj['features'])} building footprints from catalog (offline).")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(gj), encoding="utf-8")
    print(f"Wrote -> {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
