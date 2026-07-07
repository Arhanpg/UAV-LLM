"""Dharwad–Hubli location catalog and world generation."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import List

import numpy as np

from app.config import CLASSES, HAZARD_CLASSES
from app.geo.projection import dist_2d, lat_lon_to_xy
from app.models.mission import CityNode, GeoZone
from app.models.package import Package

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LOCATIONS_PATH = DATA_DIR / "locations_dharwad.json"

# Fallback inline catalog (mirrors committed JSON)
DHARWAD_LOCATIONS = [
    ("SDM Hospital & Medical College", 15.4606, 75.0168, 22.0, "hospital", "S.D.M. Hospital, Sattur Colony, Dharwad"),
    ("KIMS Hospital Dharwad", 15.4509, 75.0120, 28.0, "hospital", "Karnataka Institute of Medical Sciences, Vidyanagar"),
    ("Suretech Hospital", 15.4578, 75.0215, 15.0, "hospital", "Suretech Multi-Specialty Hospital, P.B. Road"),
    ("Navodaya Medical College", 15.4720, 75.0050, 18.0, "hospital", "Navodaya Medical College, Raichur Road, Dharwad"),
    ("Govt District Hospital Dharwad", 15.4597, 74.9989, 20.0, "hospital", "District Civil Hospital, Dharwad"),
    ("Urban Oasis Mall", 15.3649, 75.1244, 42.0, "mall", "Urban Oasis Mall, Hubli"),
    ("Akshay Park Mall", 15.3593, 75.1340, 38.0, "mall", "Akshay Park Mall, Vidya Nagar, Hubli"),
    ("Big Bazaar Dharwad", 15.4563, 75.0101, 14.0, "mall", "Big Bazaar, P.B. Road, Dharwad"),
    ("Karnataka University", 15.4570, 75.0090, 12.0, "education", "Karnataka University, Pavate Nagar, Dharwad"),
    ("BVB College of Engg", 15.3712, 75.1239, 16.0, "education", "BVB College of Engineering & Technology, Vidyanagar, Hubli"),
    ("IIT Dharwad", 15.3920, 74.9734, 10.0, "education", "Indian Institute of Technology Dharwad, WALMI Campus"),
    ("Dharwad Railway Station", 15.4603, 74.9981, 9.0, "transit", "Dharwad Junction, NH-48"),
    ("Hubli Airport", 15.3617, 75.0850, 8.0, "airbase", "Hubballi Airport (HBX), Gokul Road"),
    ("Hubli Railway Station", 15.3500, 75.1350, 10.0, "transit", "Hubli Junction — major rail hub"),
    ("KSRTC Bus Stand Dharwad", 15.4590, 74.9967, 7.0, "transit", "KSRTC Central Bus Stand, Dharwad"),
    ("Dharwad Town Hall Ground", 15.4600, 75.0077, 4.0, "park", "Town Hall Grounds, Dharwad"),
    ("Indira Gandhi Glass House Garden", 15.4560, 75.0097, 3.0, "park", "Glass House Garden, Near Unkal Lake"),
    ("Unkal Lake", 15.3760, 75.0960, 2.0, "park", "Unkal Lake, Hubli"),
    ("Dharwad Industrial Area", 15.4830, 74.9960, 18.0, "industrial", "KIADB Industrial Area, Dharwad"),
    ("Almatti Road Warehouse", 15.4420, 75.0310, 10.0, "warehouse", "Logistics Warehouse, Almatti Road, Dharwad"),
    ("Gokul Road Commercial Hub", 15.3690, 75.0800, 20.0, "commercial", "Gokul Road, Hubli — main commercial corridor"),
    ("Dharwad DC Office", 15.4591, 75.0022, 14.0, "govt", "Deputy Commissioner Office, Dharwad"),
    ("Hubli Municipal Corporation", 15.3620, 75.1250, 16.0, "govt", "Hubli-Dharwad Municipal Corporation"),
    ("Siddharoodha Math", 15.4575, 75.0116, 8.0, "religious", "Siddharoodha Math, Hubli Road, Dharwad"),
    ("Nrupatunga Betta", 15.4520, 75.0168, 5.0, "park", "Nrupatunga Betta Hillock, Dharwad"),
]


def load_locations() -> list[tuple]:
    if LOCATIONS_PATH.exists():
        with open(LOCATIONS_PATH, encoding="utf-8") as f:
            rows = json.load(f)
        return [(r["name"], r["lat"], r["lon"], r["bh"], r["cat"], r.get("desc", "")) for r in rows]
    return DHARWAD_LOCATIONS


def export_locations_json() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rows = [
        {"idx": i, "name": r[0], "lat": r[1], "lon": r[2], "bh": r[3], "cat": r[4], "desc": r[5] if len(r) > 5 else ""}
        for i, r in enumerate(DHARWAD_LOCATIONS)
    ]
    with open(LOCATIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)


def generate_world(
    loc_indices: list[int],
    pkg_requests: list[dict],
    seed: int,
    incompat_density: float,
    n_gfz: int,
    deadline_tight: float,
    hazard_mix: float,
    cap_ratio: float,
    build_compat_fn,
):
    rng = np.random.default_rng(seed)
    catalog = load_locations()
    if not loc_indices or len(loc_indices) < 2:
        loc_indices = list(range(min(12, len(catalog))))

    depot_data = catalog[loc_indices[0]]
    origin_lat, origin_lon = depot_data[1], depot_data[2]

    city: List[CityNode] = []
    for i, li in enumerate(loc_indices):
        ld = catalog[li]
        x, y = lat_lon_to_xy(ld[1], ld[2], origin_lat, origin_lon)
        city.append(
            CityNode(
                idx=i,
                lat=ld[1],
                lon=ld[2],
                x=x,
                y=y,
                building_height=ld[3],
                label=ld[0],
                category=ld[4],
                description=ld[5] if len(ld) > 5 else "",
                is_depot=(i == 0),
            )
        )

    G = build_compat_fn(incompat_density, seed)
    PKG_LABELS = {
        "PHARMA": "Insulin/Meds",
        "FOOD": "Food Package",
        "ELECTRONICS": "Device",
        "FLAMMABLE": "Fuel Canister",
        "OXIDIZER": "O₂ Cylinder",
        "CRYOGENIC": "Cryo Sample",
        "GENERAL": "General Cargo",
    }

    def sample_kappa():
        if rng.random() < hazard_mix:
            return rng.choice(
                ["PHARMA", "FLAMMABLE", "OXIDIZER", "CRYOGENIC", "ELECTRONICS"],
                p=[0.35, 0.20, 0.18, 0.12, 0.15],
            ).item()
        return rng.choice(CLASSES, p=[0.18, 0.20, 0.15, 0.07, 0.06, 0.05, 0.29]).item()

    packages: List[Package] = []
    total_w = 0.0

    if pkg_requests:
        for i, req in enumerate(pkg_requests):
            pu_name = req.get("pickup_name", "")
            dl_name = req.get("delivery_name", "")
            pu_idx = next((c.idx for c in city if pu_name.lower() in c.label.lower()), 0)
            dl_idx = next((c.idx for c in city if dl_name.lower() in c.label.lower()), min(1, len(city) - 1))
            if dl_idx == pu_idx:
                dl_idx = min(pu_idx + 1, len(city) - 1)
            kappa = req.get("kappa") or sample_kappa()
            weight = float(req.get("weight", round(rng.uniform(1.0, 5.0), 2)))
            total_w += weight
            pu_c = city[pu_idx]
            dl_c = city[dl_idx]
            d2d = dist_2d(pu_c.x, pu_c.y, dl_c.x, dl_c.y)
            dep_leg = dist_2d(city[0].x, city[0].y, pu_c.x, pu_c.y) + d2d
            slack = float(rng.uniform(40, 120)) * (1.05 - deadline_tight)
            dl = dep_leg / 15.0 + slack + float(rng.uniform(0, 25))
            pr = 1.8 if kappa == "PHARMA" else (1.4 if kappa in HAZARD_CLASSES else 1.0)
            desc = req.get("description") or f"{PKG_LABELS.get(kappa, 'Pkg')} · {pu_c.label} → {dl_c.label}"
            packages.append(
                Package(i, pu_idx, dl_idx, weight, kappa, dl, pr, kappa in {"PHARMA", "FOOD", "CRYOGENIC"}, desc)
            )
            city[pu_idx].pickups.append({"req": i, "kappa": kappa, "w": round(weight, 2), "label": PKG_LABELS.get(kappa, "Pkg")})
            city[dl_idx].drops.append({"req": i, "kappa": kappa, "w": round(weight, 2), "label": PKG_LABELS.get(kappa, "Pkg")})
    else:
        n_auto = max(3, min(8, len(city) - 1))
        for i in range(n_auto):
            kappa = sample_kappa()
            pi_idx = int(rng.integers(1, len(city)))
            di_idx = int(rng.integers(1, len(city)))
            while di_idx == pi_idx:
                di_idx = int(rng.integers(1, len(city)))
            weight = float(round(rng.uniform(1.0, 6.0), 2))
            total_w += weight
            pu_c = city[pi_idx]
            dl_c = city[di_idx]
            d2d = dist_2d(pu_c.x, pu_c.y, dl_c.x, dl_c.y)
            dep_leg = dist_2d(city[0].x, city[0].y, pu_c.x, pu_c.y) + d2d
            slack = float(rng.uniform(40, 120)) * (1.05 - deadline_tight)
            dl_t = dep_leg / 15.0 + slack + float(rng.uniform(0, 25))
            pr = 1.8 if kappa == "PHARMA" else (1.4 if kappa in HAZARD_CLASSES else 1.0)
            desc = f"{PKG_LABELS.get(kappa, 'Pkg')} · {pu_c.label} → {dl_c.label}"
            packages.append(
                Package(i, pi_idx, di_idx, weight, kappa, dl_t, pr, kappa in {"PHARMA", "FOOD", "CRYOGENIC"}, desc)
            )
            city[pi_idx].pickups.append({"req": i, "kappa": kappa, "w": round(weight, 2), "label": PKG_LABELS.get(kappa, "Pkg")})
            city[di_idx].drops.append({"req": i, "kappa": kappa, "w": round(weight, 2), "label": PKG_LABELS.get(kappa, "Pkg")})

    W_cap = max(8.0, cap_ratio * total_w)

    tall = sorted(city, key=lambda c: c.building_height, reverse=True)
    gzones: List[GeoZone] = []
    nzones: List[GeoZone] = []
    for i in range(min(n_gfz, len(tall))):
        c = tall[i]
        ox = float(rng.uniform(-50, 50))
        oy = float(rng.uniform(-50, 50))
        gz_lat = c.lat + (oy / 111111)
        gz_lon = c.lon + (ox / (111111 * math.cos(math.radians(c.lat))))
        gzones.append(
            GeoZone(
                lat=gz_lat, lon=gz_lon, x=c.x + ox, y=c.y + oy,
                radius=float(rng.uniform(80, 180)), kind="nofly", label=f"No-Fly near {c.label}",
            )
        )
        ox2 = float(rng.uniform(-80, 80))
        oy2 = float(rng.uniform(-80, 80))
        nz_lat = c.lat + (oy2 / 111111)
        nz_lon = c.lon + (ox2 / (111111 * math.cos(math.radians(c.lat))))
        nzones.append(
            GeoZone(
                lat=nz_lat, lon=nz_lon, x=c.x + ox2, y=c.y + oy2,
                radius=float(rng.uniform(100, 250)), kind="noise", label=f"Noise Zone {i + 1}",
            )
        )

    traj_xy = [(city[0].x, city[0].y)]
    traj_gps = [(city[0].lat, city[0].lon)]
    for p in packages:
        cx = city[p.pickup_loc]
        traj_xy.append((cx.x, cx.y))
        traj_gps.append((cx.lat, cx.lon))
    for p in packages:
        cx = city[p.delivery_loc]
        traj_xy.append((cx.x, cx.y))
        traj_gps.append((cx.lat, cx.lon))
    traj_xy.append((city[0].x, city[0].y))
    traj_gps.append((city[0].lat, city[0].lon))

    return city, packages, G, gzones, nzones, W_cap, traj_xy, traj_gps
