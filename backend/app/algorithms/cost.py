"""Multi-objective cost J(π) and route evaluation (Paper 2 Eq. 5–6)."""

import math
from typing import List

from app.algorithms.compat_graph import clique_ok
from app.algorithms.routing import node_role
from app.config import ALPHA_OBJ, PENALTIES, UAV_SPEED
from app.geo.projection import dist_2d
from app.models.mission import CityNode, GeoZone


def seg_hits_zone(ax: float, ay: float, bx: float, by: float, z: GeoZone) -> bool:
    cx, cy = z.x, z.y
    abx, aby = bx - ax, by - ay
    denom = abx * abx + aby * aby
    if denom < 1e-12:
        return (ax - cx) ** 2 + (ay - cy) ** 2 <= z.radius ** 2
    t = max(0.0, min(1.0, ((cx - ax) * abx + (cy - ay) * aby) / denom))
    px, py = ax + t * abx, ay + t * aby
    return (px - cx) ** 2 + (py - cy) ** 2 <= z.radius ** 2


def geo_penalty(ax: float, ay: float, bx: float, by: float, gzones: List[GeoZone]) -> float:
    return sum(dist_2d(ax, ay, bx, by) for z in gzones if seg_hits_zone(ax, ay, bx, by, z))


def energy_3d(d3: float, payload: float, wind_comp: float = 0.0) -> float:
    from app.config import ROTOR_K

    return d3 * (1.0 + ROTOR_K * payload) + wind_comp


def wind_penalty(ax: float, ay: float, bx: float, by: float, wind_dir: float = 270.0, wind_spd: float = 6.0) -> float:
    dx, dy = bx - ax, by - ay
    angle = math.degrees(math.atan2(dy, dx)) % 360
    diff = abs(angle - wind_dir) % 360
    if diff > 180:
        diff = 360 - diff
    hw = math.cos(math.radians(diff))
    return dist_2d(ax, ay, bx, by) * max(0, hw) * wind_spd * 0.002


def evaluate(
    traj_xy,
    city_nodes: List[CityNode],
    packages,
    route,
    G,
    gzones: List[GeoZone],
    nzones: List[GeoZone],
    synth=None,
    W: float = 20.0,
    wind_dir: float = 270.0,
):
    n = len(packages)
    onboard = set()
    delivered = set()
    y = 0.0
    t = 0.0
    dist = en = noise = lateness = 0.0
    cv = gv = pv = rv = 0
    seen = set()
    depot_ok = 1 if (route and route[0] == 0 and route[-1] == 2 * n + 1) else 0
    for s in range(len(route) - 1):
        u, v = route[s], route[s + 1]
        ax, ay = traj_xy[u]
        bx, by = traj_xy[v]
        seg2d = dist_2d(ax, ay, bx, by)
        seg3d = math.sqrt(seg2d**2 + 6.0**2)
        dist += seg2d
        wp = wind_penalty(ax, ay, bx, by, wind_dir)
        en += energy_3d(seg3d, y, wp)
        noise += sum(seg2d for z in nzones if seg_hits_zone(ax, ay, bx, by, z))
        if any(seg_hits_zone(ax, ay, bx, by, z) for z in gzones):
            gv += 1
        t += seg2d / UAV_SPEED
        tp, rid = node_role(v, n)
        if tp in {"P", "D"}:
            if v in seen:
                rv += 1
            seen.add(v)
        if tp == "P":
            pkg = packages[rid]
            y += pkg.weight
            onboard.add(rid)
        elif tp == "D":
            pkg = packages[rid]
            if rid not in onboard:
                rv += 1
            else:
                y -= pkg.weight
                onboard.remove(rid)
                delivered.add(rid)
                lateness += max(0, t - pkg.deadline) * pkg.priority
        if y < -1e-6 or y - W > 1e-6:
            pv += 1
        kk = [(synth[i] if synth else packages[i].kappa) for i in onboard]
        if not clique_ok(kk, G):
            cv += 1
    expected = set(range(1, 2 * n + 1))
    missed = len(expected - seen) + len(seen - expected) + rv + (0 if depot_ok else 1)
    total_viol = cv + gv + pv + rv + missed
    cost = (
        ALPHA_OBJ["distance"] * dist
        + ALPHA_OBJ["lateness"] * lateness
        + ALPHA_OBJ["noise"] * noise
        + ALPHA_OBJ["energy"] * en
        + PENALTIES["compat"] * cv
        + PENALTIES["geo"] * gv
        + PENALTIES["payload"] * pv
        + PENALTIES["precedence"] * rv
        + PENALTIES["missed"] * missed
    )
    return {
        "cost": cost,
        "dist": round(dist, 2),
        "lateness": round(lateness, 3),
        "noise": round(noise, 2),
        "energy": round(en, 2),
        "cv": cv,
        "gv": gv,
        "pv": pv,
        "rv": rv,
        "missed": missed,
        "viol": total_viol,
        "feasible": total_viol == 0,
        "delivered": len(delivered),
        "n": n,
        "time_s": round(t, 1),
        "battery_pct": round(max(0, 100 - en / 50), 1),
    }
