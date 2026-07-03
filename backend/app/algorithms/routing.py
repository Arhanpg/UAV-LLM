"""Greedy route construction and node role helpers."""

from app.algorithms.compat_graph import clique_ok
from app.algorithms.mpdd import node_role  # canonical node_role, re-exported
from app.config import UAV_SPEED
from app.geo.projection import dist_2d

__all__ = ["node_role", "feasible_cands", "build_route"]


def feasible_cands(packages, U, onboard, y, synth, G, W, compat_check):
    n = len(packages)
    C = []
    active = [synth[i] for i in onboard]
    for node in U:
        tp, rid = node_role(node, n)
        if tp == "P":
            pkg = packages[rid]
            if y + pkg.weight <= W + 1e-9:
                kk = synth[rid]
                if (not compat_check) or clique_ok(active + [kk], G):
                    C.append(node)
        elif tp == "D" and rid in onboard:
            C.append(node)
    return C


def build_route(packages, traj_xy, synth, G, gzones, W, compat_check, score_fn, label):
    n = len(packages)
    start = 0
    end = 2 * n + 1
    route = [start]
    U = set(range(1, 2 * n + 1))
    onboard = set()
    y = 0.0
    t = 0.0
    log = []
    safety = 0
    while U and safety < 20 * (2 * n + 2):
        safety += 1
        C = feasible_cands(packages, U, onboard, y, synth, G, W, compat_check)
        if not C:
            unpicked = [j for j in U if node_role(j, n)[0] == "P"]
            if not unpicked:
                break
            C = unpicked
        if not C:
            break
        sc = score_fn(C, route[-1], onboard, U, t)
        jstar = max(C, key=lambda j: sc.get(j, 0))
        prev = route[-1]
        seg = dist_2d(*traj_xy[prev], *traj_xy[jstar])
        log.append(
            {
                "algo": label,
                "node": jstar,
                "score": round(sc.get(jstar, 0), 3),
                "candidates": len(C),
                "onboard": len(onboard),
                "payload": round(y, 2),
                "dist_seg": round(seg, 1),
            }
        )
        route.append(jstar)
        t += seg / UAV_SPEED
        tp, rid = node_role(jstar, n)
        if tp == "P":
            onboard.add(rid)
            y += packages[rid].weight
        elif tp == "D" and rid in onboard:
            onboard.remove(rid)
            y -= packages[rid].weight
        U.discard(jstar)
    if route[-1] != end:
        route.append(end)
    return route, log
