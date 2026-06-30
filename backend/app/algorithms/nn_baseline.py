"""Nearest-neighbor PDP baseline."""

from app.geo.projection import dist_2d


def nn_scores(traj_xy, cands, cur):
    cpos = traj_xy[cur]
    dists = {j: max(1e-6, dist_2d(*cpos, *traj_xy[j])) for j in cands}
    dmin = min(dists.values())
    return {j: dmin / dists[j] for j in cands}
