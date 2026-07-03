"""Phase 2 — corridor-based altitude planning tests."""

from app.algorithms.altitude import corridor_cruise_altitude, rate_limited_profile
from app.config import ALT_SAFETY_MARGIN, MAX_CEILING, MIN_ALT
from app.geo.buildings import BuildingIndex, Footprint, load_building_index


def test_segment_over_tall_building_climbs_above_it():
    # A 60 m building sitting right on the flight path.
    idx = BuildingIndex([Footprint(cx=50.0, cy=0.0, radius=10.0, height=60.0)])
    alt = corridor_cruise_altitude(0, 0, 100, 0, idx)
    assert alt >= 60.0 + ALT_SAFETY_MARGIN - 1e-9
    assert alt <= MAX_CEILING


def test_clear_segment_stays_at_min_altitude():
    idx = BuildingIndex([Footprint(cx=0.0, cy=500.0, radius=10.0, height=80.0)])  # far away
    alt = corridor_cruise_altitude(0, 0, 100, 0, idx)
    assert abs(alt - MIN_ALT) < 1e-9


def test_no_index_returns_min_altitude():
    assert corridor_cruise_altitude(0, 0, 100, 0, None) == MIN_ALT


def test_ceiling_clamp():
    idx = BuildingIndex([Footprint(cx=50.0, cy=0.0, radius=10.0, height=500.0)])
    assert corridor_cruise_altitude(0, 0, 100, 0, idx) == MAX_CEILING


def test_building_outside_corridor_is_ignored():
    # 60 m building 40 m off the path; corridor half-width 7.5 m + radius 5 m < 40.
    idx = BuildingIndex([Footprint(cx=50.0, cy=40.0, radius=5.0, height=60.0)])
    assert corridor_cruise_altitude(0, 0, 100, 0, idx) == MIN_ALT


def test_rate_limited_profile_no_teleport():
    pts = [(0, 0), (300, 0), (600, 0)]
    cruise = [MIN_ALT, 110.0, MIN_ALT]
    profile = rate_limited_profile(pts, cruise, vspeed=3.0, speed=15.0, samples_per_seg=10)
    assert profile[0]["z"] == MIN_ALT
    # consecutive z steps never jump more than the physical limit allows (+slack)
    zs = [p["z"] for p in profile]
    max_jump = max(abs(zs[i + 1] - zs[i]) for i in range(len(zs) - 1))
    assert max_jump < 20.0  # gradual, not an instantaneous 80 m teleport


def test_load_building_index_from_committed_geojson():
    # Dharwad depot origin — the committed GeoJSON should project some footprints.
    idx = load_building_index(15.4606, 75.0168)
    assert len(idx) > 0
    assert all(fp.height > 0 for fp in idx.footprints)
