"""Z3-backed formal verifier V (Paper 2 Eq. 7d) — spec §8.3.

Two independent responsibilities:

1. ``verify_psi`` — structural sanity of a synthesized constraint tuple Ψ(r_i):
   τ_min < τ_max, deadline > 0, κ ∈ K, and (when a zone set is supplied) every
   geofence reference resolves to a known zone. Encoded and checked with Z3.

2. ``verify_route`` — a *second, independent* feasibility re-check of a
   constructed route: payload bounds (0 ≤ y ≤ W) via real arithmetic, the
   active-set clique constraint as boolean SAT over G, pickup-before-delivery
   precedence, and deadline inequalities. This is run separately from the
   heuristic algorithm's own bookkeeping in cost.py; ``discrepancy`` flags any
   disagreement so the UI can surface it rather than silently trusting one side.
"""

from __future__ import annotations

import itertools
from typing import Optional

import z3

from app.algorithms.mpdd import node_role
from app.config import CLASSES, UAV_SPEED
from app.geo.projection import dist_2d


def verify_psi(psi: dict, known_zones: Optional[list[str]] = None, classes=CLASSES) -> dict:
    """Structural verification of one Ψ tuple. Returns {ok, reasons, checks}."""
    reasons: list[str] = []
    checks = {}

    s = z3.Solver()
    tmin = z3.Real("tmin")
    tmax = z3.Real("tmax")
    s.add(tmin == float(psi["temp_min"]), tmax == float(psi["temp_max"]), tmin < tmax)
    envelope_ok = s.check() == z3.sat
    checks["temp_envelope"] = envelope_ok
    if not envelope_ok:
        reasons.append(f"temperature envelope empty: [{psi['temp_min']}, {psi['temp_max']}]")

    deadline_ok = True
    if psi.get("deadline_minutes") is not None:
        sd = z3.Solver()
        dl = z3.Real("dl")
        sd.add(dl == float(psi["deadline_minutes"]), dl > 0)
        deadline_ok = sd.check() == z3.sat
        if not deadline_ok:
            reasons.append(f"non-positive deadline: {psi['deadline_minutes']}")
    checks["deadline"] = deadline_ok

    class_ok = psi.get("kappa") in classes
    checks["class"] = class_ok
    if not class_ok:
        reasons.append(f"unknown commodity class: {psi.get('kappa')}")

    zones_ok = True
    if known_zones is not None:
        known_lc = {z.lower() for z in known_zones}
        for z in psi.get("prohibited_zones", []):
            zl = z.lower()
            if not any(zl == k or k in zl or zl in k for k in known_lc):
                zones_ok = False
                reasons.append(f"unresolved geofence reference: {z}")
    checks["zones"] = zones_ok

    return {"ok": envelope_ok and deadline_ok and class_ok and zones_ok, "reasons": reasons, "checks": checks}


def verify_route(
    route,
    packages,
    synth,
    G,
    W,
    traj_xy=None,
    speed: float = UAV_SPEED,
) -> dict:
    """Independent Z3 feasibility re-check of a full route."""
    n = len(packages)
    reasons: list[str] = []

    # --- Payload bounds via real arithmetic (0 ≤ y ≤ W). ---
    s = z3.Solver()
    ys = [z3.Real(f"y_{k}") for k in range(len(route))]
    s.add(ys[0] == 0)
    onboard: set[int] = set()
    precedence_ok = True
    for k in range(1, len(route)):
        tp, rid = node_role(route[k], n)
        if tp == "P":
            s.add(ys[k] == ys[k - 1] + float(packages[rid].weight))
            onboard.add(rid)
        elif tp == "D":
            if rid not in onboard:
                precedence_ok = False
                reasons.append(f"delivery of pkg {rid} before pickup (step {k})")
                s.add(ys[k] == ys[k - 1])
            else:
                s.add(ys[k] == ys[k - 1] - float(packages[rid].weight))
                onboard.discard(rid)
        else:
            s.add(ys[k] == ys[k - 1])
    for k in range(len(route)):
        s.add(ys[k] >= 0, ys[k] <= float(W))
    payload_ok = s.check() == z3.sat
    if not payload_ok:
        reasons.append("payload bound 0 ≤ y ≤ W is unsatisfiable")

    # --- Active-set clique constraint as boolean SAT over G (Eq. 4). ---
    clique_ok = True
    cs = z3.Solver()
    edge_vars: dict[tuple, z3.BoolRef] = {}

    def edge(a, b):
        key = tuple(sorted((a, b)))
        if key not in edge_vars:
            v = z3.Bool(f"e_{key[0]}_{key[1]}")
            edge_vars[key] = v
            cs.add(v == bool(G.get((a, b), True))) if G is not None else cs.add(v)
        return edge_vars[key]

    onboard = set()
    required = []
    for k in range(1, len(route)):
        tp, rid = node_role(route[k], n)
        if tp == "P":
            onboard.add(rid)
        elif tp == "D":
            onboard.discard(rid)
        active = [synth[i] if synth else packages[i].kappa for i in onboard]
        for a, b in itertools.combinations(set(active), 2):
            required.append(edge(a, b))
    if required:
        cs.add(z3.And(*required))
    clique_ok = cs.check() == z3.sat
    if not clique_ok:
        reasons.append("active onboard set violates the Gc clique constraint")

    # --- Deadlines (optional; needs geometry). ---
    deadline_ok = True
    if traj_xy is not None:
        t = 0.0
        for k in range(1, len(route)):
            ax, ay = traj_xy[route[k - 1]]
            bx, by = traj_xy[route[k]]
            t += dist_2d(ax, ay, bx, by) / speed
            tp, rid = node_role(route[k], n)
            if tp == "D":
                dl = getattr(packages[rid], "deadline", None)
                if dl is not None and t > dl + 1e-6:
                    deadline_ok = False
                    reasons.append(f"pkg {rid} delivered at t={t:.1f}s > deadline {dl:.1f}s")

    ok = payload_ok and clique_ok and precedence_ok and deadline_ok
    return {
        "ok": ok,
        "payload_ok": payload_ok,
        "clique_ok": clique_ok,
        "precedence_ok": precedence_ok,
        "deadline_ok": deadline_ok,
        "reasons": reasons,
    }


def discrepancy(smt_result: dict, evaluate_result: dict) -> Optional[str]:
    """Compare the Z3 verdict against cost.evaluate's feasibility bookkeeping.

    Returns a human-readable message when they disagree, else None.
    """
    # Compare only the hard constraints both sides actually model: payload (pv),
    # clique/compat (cv), and precedence (rv). cost.evaluate's overall `feasible`
    # flag additionally folds in geofence/missed nodes and deadline lateness,
    # which the Z3 route check does not encode — so those are excluded here.
    if not all(k in evaluate_result for k in ("cv", "pv", "rv")):
        return None
    cost_hard = evaluate_result["cv"] == 0 and evaluate_result["pv"] == 0 and evaluate_result["rv"] == 0
    smt_hard = (
        smt_result.get("payload_ok", True)
        and smt_result.get("clique_ok", True)
        and smt_result.get("precedence_ok", True)
    )
    if smt_hard != cost_hard:
        return (
            f"VERIFIER DISCREPANCY: Z3 says {'feasible' if smt_hard else 'infeasible'} "
            f"but cost.evaluate says {'feasible' if cost_hard else 'infeasible'} "
            f"(cv={evaluate_result['cv']}, pv={evaluate_result['pv']}, rv={evaluate_result['rv']})"
        )
    return None
