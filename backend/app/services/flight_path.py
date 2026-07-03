"""Flight path builder for 3D visualization."""

from app.algorithms.altitude import corridor_cruise_altitude, rate_limited_profile
from app.algorithms.routing import node_role
from app.config import MIN_ALT, UAV_SPEED
from app.geo.buildings import load_building_index
from app.geo.projection import dist_2d


def altitude_profile(route, traj_xy, city_nodes):
    """Rate-limited 3D vertical profile for the whole route (spec §8.4)."""
    bindex = load_building_index(city_nodes[0].lat, city_nodes[0].lon) if city_nodes else None
    pts = [traj_xy[nd] for nd in route]
    cruise = [MIN_ALT]
    for k in range(1, len(route)):
        ax, ay = traj_xy[route[k - 1]]
        bx, by = traj_xy[route[k]]
        cruise.append(corridor_cruise_altitude(ax, ay, bx, by, bindex))
    return rate_limited_profile(pts, cruise), cruise


def build_flight_path(route, traj_xy, traj_gps, city_nodes, packages):
    n = len(packages)
    bindex = load_building_index(city_nodes[0].lat, city_nodes[0].lon) if city_nodes else None
    steps = []
    y = 0.0
    t = 0.0
    PKG_EMOJIS = {
        "PHARMA": "💊",
        "FOOD": "🍱",
        "ELECTRONICS": "💻",
        "FLAMMABLE": "🔥",
        "OXIDIZER": "⚗️",
        "CRYOGENIC": "❄️",
        "GENERAL": "📦",
    }
    for si, nd in enumerate(route):
        if si == 0:
            steps.append(
                {
                    "step": 0,
                    "node": nd,
                    "x": traj_xy[nd][0],
                    "y": traj_xy[nd][1],
                    "lat": traj_gps[nd][0],
                    "lon": traj_gps[nd][1],
                    "alt": MIN_ALT,
                    "role": "DEPOT",
                    "req": -1,
                    "label": city_nodes[0].label,
                    "dist": 0.0,
                    "payload": 0.0,
                    "time": 0.0,
                    "algo_info": {"action": "TAKEOFF", "payload": 0, "altitude": MIN_ALT},
                }
            )
            continue
        prev = route[si - 1]
        ax, ay = traj_xy[prev]
        bx, by = traj_xy[nd]
        alt = corridor_cruise_altitude(ax, ay, bx, by, bindex)
        seg2d = dist_2d(ax, ay, bx, by)
        t += seg2d / UAV_SPEED
        tp, rid = node_role(nd, n)
        if tp == "P":
            y += packages[rid].weight
            k = packages[rid].kappa
            action = f"{PKG_EMOJIS.get(k, '📦')} PICKUP pkg#{rid} ({k}) {packages[rid].weight}kg"
            nd_label = city_nodes[packages[rid].pickup_loc].label if packages[rid].pickup_loc < len(city_nodes) else f"Node {nd}"
        elif tp == "D":
            if rid < len(packages):
                y = max(0, y - packages[rid].weight)
            k = packages[rid].kappa if rid < len(packages) else "GENERAL"
            action = f"✅ DELIVER pkg#{rid} ({k})"
            nd_label = (
                city_nodes[packages[rid].delivery_loc].label
                if rid < len(packages) and packages[rid].delivery_loc < len(city_nodes)
                else f"Node {nd}"
            )
        else:
            action = "🏠 RETURN to depot"
            nd_label = city_nodes[0].label
        steps.append(
            {
                "step": si,
                "node": nd,
                "x": traj_xy[nd][0],
                "y": traj_xy[nd][1],
                "lat": traj_gps[nd][0],
                "lon": traj_gps[nd][1],
                "alt": round(alt, 1),
                "role": tp,
                "req": rid,
                "label": nd_label,
                "dist": round(seg2d, 1),
                "payload": round(y, 2),
                "time": round(t, 1),
                "algo_info": {"action": action, "payload": round(y, 2), "altitude": round(alt, 1)},
            }
        )
    return steps
