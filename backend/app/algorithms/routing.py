"""Greedy route construction and node role helpers."""

from app.algorithms.compat_graph import clique_ok
from app.algorithms.mpdd import node_role  # canonical node_role, re-exported
from app.config import UAV_SPEED
from app.geo.projection import dist_2d
from app.ws.telemetry import emit

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


def build_route(
    packages, traj_xy, synth, G, gzones, W, compat_check, score_fn, label, telemetry=False,
    start_node=0, init_U=None, init_onboard=None, init_y=0.0,
):
    """Greedy construction. For mid-mission replanning (Eq. 8a), pass
    ``start_node`` (drone's current node), the remaining unserved node set
    ``init_U``, the currently-onboard package ids ``init_onboard``, and the
    current payload ``init_y``."""
    n = len(packages)
    start = start_node
    end = 2 * n + 1
    route = [start]
    U = set(range(1, 2 * n + 1)) if init_U is None else set(init_U)
    onboard = set() if init_onboard is None else set(init_onboard)
    y = init_y
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
        entry = {
            "algo": label,
            "node": jstar,
            "score": round(sc.get(jstar, 0), 3),
            "candidates": len(C),
            "onboard": len(onboard),
            "payload": round(y, 2),
            "dist_seg": round(seg, 1),
        }
        log.append(entry)
        if telemetry:
            top = sorted(({"node": j, "role": node_role(j, n)[0], "score": round(sc.get(j, 0), 3)} for j in C),
                         key=lambda d: d["score"], reverse=True)[:6]
            emit(
                "phase1_step",
                algo=label,
                step=len(route),
                selected=jstar,
                selected_role=node_role(jstar, n)[0],
                score=entry["score"],
                payload=entry["payload"],
                cap=round(W, 2),
                candidates=top,
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
    if telemetry:
        emit("phase1_complete", algo=label, route_len=len(route), route=route)
    return route, log
