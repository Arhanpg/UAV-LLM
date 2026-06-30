"""MPDD greedy fitness scoring (Paper 1 Eq. 4–7)."""

from app.algorithms.routing import node_role
from app.geo.projection import dist_2d


def mpdd_scores(traj_xy, packages, cands, cur, n):
    cpos = traj_xy[cur]
    dists = {j: max(1e-6, dist_2d(*cpos, *traj_xy[j])) for j in cands}
    dmin = min(dists.values())
    vals = {j: packages[node_role(j, n)[1]].weight if node_role(j, n)[1] >= 0 else 1.0 for j in cands}
    vm = max(vals.values(), default=1.0)
    return {j: 0.6 * (dmin / dists[j]) + 0.4 * (vals[j] / vm) for j in cands}
