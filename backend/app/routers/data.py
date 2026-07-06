"""Static / derived data endpoints (spec §8.1)."""

from fastapi import APIRouter

from app.algorithms.compat_graph import build_compat
from app.config import CLASSES, FIXED_INCOMPAT
from app.geo.buildings import buildings_geojson
from app.geo.locations import load_locations

router = APIRouter(prefix="/api", tags=["data"])


@router.get("/locations")
async def get_locations():
    catalog = load_locations()
    return {
        "locations": [
            {"idx": i, "name": loc[0], "lat": loc[1], "lon": loc[2], "bh": loc[3], "cat": loc[4],
             "desc": loc[5] if len(loc) > 5 else ""}
            for i, loc in enumerate(catalog)
        ]
    }


@router.get("/buildings")
async def get_buildings():
    return buildings_geojson()


@router.get("/compat-graph")
async def get_compat_graph(density: float = 0.25, seed: int = 42):
    G = build_compat(density, seed)
    edges = [{"a": a, "b": b, "compatible": ok} for (a, b), ok in G.items() if a < b]
    return {
        "classes": CLASSES,
        "edges": edges,
        "fixed_incompatible": [list(p) for p in FIXED_INCOMPAT],
        "incompatible_pairs": [[a, b] for (a, b), ok in G.items() if not ok and a < b],
    }
