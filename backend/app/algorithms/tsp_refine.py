"""Phase 2 trajectory refinement — Paper 1 Algorithm 1 (exact control flow).

Sub-trajectories are delimited by consecutive source (pickup) positions. Each is
re-solved as an open TSP (fixed start, fixed end) via an MST-preorder
approximation [13]. The extend-then-fallback control flow, including the
``i ← max(i+1, j-1)`` backtrack, follows Algorithm 1 line-for-line.
"""

from app.algorithms.cost import evaluate
from app.algorithms.mpdd import node_role
from app.geo.projection import dist_2d
from app.ws.telemetry import emit


def mst_preorder_tsp(nodes, traj_xy):
    """Open-TSP approximation over ``nodes`` with fixed first/last node.

    Builds a minimum spanning tree (Prim) over the node set rooted at the start
    node, takes a preorder traversal to order the visit, then forces the tour to
    *end* at the fixed terminal node rather than return to the root (Paper 1
    §III-B). O(k^2) in the sub-trajectory length k → O((m')^2) overall.
    """
    if len(nodes) <= 2:
        return nodes[:]
    start, end = nodes[0], nodes[-1]
    pts = {nd: traj_xy[nd] for nd in nodes}

    # Prim's MST rooted at the start node.
    in_tree = {start}
    children: dict[int, list[int]] = {nd: [] for nd in nodes}
    remaining = set(nodes) - {start}
    while remaining:
        best_edge = None
        best_d = float("inf")
        for u in in_tree:
            ux, uy = pts[u]
            for v in remaining:
                d = dist_2d(ux, uy, *pts[v])
                if d < best_d:
                    best_d, best_edge = d, (u, v)
        u, v = best_edge
        children[u].append(v)
        in_tree.add(v)
        remaining.discard(v)

    # Preorder traversal from the root (nearest child first).
    order: list[int] = []
    stack = [start]
    while stack:
        nd = stack.pop()
        order.append(nd)
        kids = sorted(children[nd], key=lambda c: dist_2d(*pts[nd], *pts[c]), reverse=True)
        stack.extend(kids)

    # Force the fixed start first and the fixed terminal last (open TSP).
    return [start] + [nd for nd in order if nd not in (start, end)] + [end]


def _source_positions(route, n):
    """1-indexed source-position array s[]: s[1..m'] are pickup positions in the
    route; s[m'+1] is the final depot position (Paper 1 §III-B)."""
    pos = [None]  # s[0] unused (1-indexed to mirror the paper)
    pos.extend(p for p, nd in enumerate(route) if node_role(nd, n)[0] == "P")
    pos.append(len(route) - 1)  # s[m'+1] = return-to-depot
    return pos


def _route_dist(route, traj_xy):
    return sum(
        dist_2d(*traj_xy[route[k]], *traj_xy[route[k + 1]]) for k in range(len(route) - 1)
    )


def refine(packages, traj_xy, route, synth, G, W, gzones, nzones=None, city_nodes=None, telemetry=False):
    """Algorithm 1 — return a refined copy of ``route``."""
    n = len(packages)
    route = route[:]
    gzones = gzones if gzones is not None else []
    nzones = nzones if nzones is not None else []
    city_nodes = city_nodes if city_nodes is not None else []
    # Number of sources actually present in this route (a replan suffix may
    # carry fewer than the full n, so we count rather than assume).
    m_prime = sum(1 for nd in route if node_role(nd, n)[0] == "P")

    def feasible(rt):
        m = evaluate(traj_xy, city_nodes, packages, rt, G, gzones, nzones, synth, W)
        return m.get("pv", 0) == 0 and m.get("rv", 0) == 0 and m.get("cv", 0) == 0

    i = 1
    guard = 0
    while i < m_prime + 1 and guard < 4 * (m_prime + 2) ** 2:
        guard += 1
        s = _source_positions(route, n)  # recompute; sub-TSP preserves positions
        if s[i + 1] - s[i] > 2:
            advanced = False
            for j in range(i + 1, m_prime + 2):
                start, end = s[i], s[j]
                tra = route[start : end + 1]
                new_tra = mst_preorder_tsp(tra, traj_xy)
                d_old = _route_dist(tra, traj_xy)
                d_new = _route_dist(new_tra, traj_xy)
                cand = route[:start] + new_tra + route[end + 1 :]
                ok = feasible(cand)
                accepted = d_new <= d_old + 1e-9 and ok
                if telemetry:
                    emit(
                        "phase2_mst_built",
                        i=i, j=j, start=start, end=end, sub_len=len(tra), order=new_tra,
                    )
                    emit(
                        "phase2_subtrajectory_attempt",
                        i=i, j=j, d_old=round(d_old, 1), d_new=round(d_new, 1),
                        feasible=ok, accepted=accepted,
                    )
                if accepted:
                    route = cand  # replace and keep extending (j+1)
                else:
                    i = max(i + 1, j - 1)
                    advanced = True
                    break
            if not advanced:
                i = m_prime + 1  # extended to the depot — done
        else:
            i += 1
    if telemetry:
        emit("phase2_refine_result", route=route, dist=round(_route_dist(route, traj_xy), 1))
    return route
