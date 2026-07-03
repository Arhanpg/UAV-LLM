"""MPDD greedy construction — Paper 1 Eq. 2-7.

Node encoding (0-based package ids, 1-based node ids in the trajectory):
    node 0            -> depot start (l0)
    node 1 .. n       -> dummy sources s'_i  (package i-1)
    node n+1 .. 2n    -> dummy dests   d'_i  (package i-1)
    node 2n+1         -> depot end   (l0)

Implements the load-aware delta (Eq. 2-3), the normalized distance/weight
fitness (Eq. 4-6), and the greedy selection (Eq. 7). ``node_role`` is defined
here as the canonical helper; other modules import it from this module.
"""

from app.config import MPDD_ALPHA
from app.geo.projection import dist_2d


def node_role(node: int, n: int) -> tuple[str, int]:
    """Map a trajectory node id to (role, package_id).

    role in {"P" (source), "D" (destination), "DEPOT"}; package_id is 0-based,
    or -1 for the depot.
    """
    if 1 <= node <= n:
        return "P", node - 1
    if n + 1 <= node <= 2 * n:
        return "D", node - (n + 1)
    return "DEPOT", -1


def compute_delta(node, node_role_fn, packages, onboard, K_i_fn):
    """Load-aware package weight δ (Paper 1, Eq. 2-3).

    δ(d'_i) = w'_i                                   (Eq. 3)
    δ(s'_i) = w'_i + Σ_{j' ∈ K_i} δ(j')              (Eq. 2)

    K_i is the set of dummy destinations co-located with source s'_i whose
    packages are already on board (droppable the moment the UAV lands at s'_i).
    ``K_i_fn(node, onboard)`` returns those destination node ids.
    """
    typ, rid = node_role_fn(node, len(packages))
    w = packages[rid].weight
    if typ == "P":
        colocated = K_i_fn(node, onboard)
        return w + sum(
            compute_delta(j, node_role_fn, packages, onboard, K_i_fn) for j in colocated
        )
    return w  # destination (Eq. 3)


def mpdd_fitness_score(dmin, dist_ij, delta_j, wmax, alpha=MPDD_ALPHA):
    """Normalized distance/weight fitness (Paper 1, Eq. 6).

    f(i', j') = α · (d_min / dis(i', j')) + (1-α) · (δ(j') / w_max)
    """
    dist_ij = max(1e-6, dist_ij)
    wmax = max(1e-9, wmax)
    return alpha * (dmin / dist_ij) + (1.0 - alpha) * (delta_j / wmax)


def _colocated_ready_dests(node, packages, onboard, n):
    """K_i: dummy destinations physically co-located with source ``node`` whose
    package has already been picked up (Eq. 2)."""
    _, rid = node_role(node, n)
    src_loc = packages[rid].pickup_loc
    return [oid + n + 1 for oid in onboard if packages[oid].delivery_loc == src_loc]


def mpdd_scores(traj_xy, packages, cands, cur, n, onboard=None):
    """Fitness of every candidate node from the current node (Eq. 4-7).

    Paper tie-break: a zero-distance dummy source is chosen directly (heaviest δ
    first). Realized here because the (d_min / dis) term → ∞ as dis → 0, so a
    co-located candidate dominates the ranking, and among several the heaviest δ
    wins via the weight term.
    """
    onboard = set() if onboard is None else onboard
    cpos = traj_xy[cur]
    dists = {j: dist_2d(*cpos, *traj_xy[j]) for j in cands}
    dmin = min((d for d in dists.values() if d > 1e-9), default=1e-6)

    def K_i(nd, ob):
        return _colocated_ready_dests(nd, packages, ob, n)

    deltas = {}
    for j in cands:
        typ, rid = node_role(j, n)
        if rid < 0:
            deltas[j] = 1.0
        elif typ == "P":
            deltas[j] = compute_delta(j, node_role, packages, onboard, K_i)
        else:
            deltas[j] = packages[rid].weight
    wmax = max(deltas.values(), default=1.0)
    return {
        j: mpdd_fitness_score(dmin, max(1e-6, dists[j]), deltas[j], wmax)
        for j in cands
    }
