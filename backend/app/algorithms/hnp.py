"""HNP semantic-aware scoring (Paper 2 extension)."""

from app.algorithms.compat_graph import clique_ok
from app.algorithms.cost import geo_penalty
from app.algorithms.routing import node_role
from app.geo.projection import dist_2d


def blocks_future(rid, onboard, U, synth, packages, G, n):
    if rid not in onboard:
        return 0
    before = [synth[i] for i in onboard]
    after = [synth[i] for i in onboard if i != rid]
    for uk in U:
        utp, uid = node_role(uk, n)
        if utp == "P":
            ck = synth[uid]
            if not clique_ok(before + [ck], G) and clique_ok(after + [ck], G):
                return 1
    return 0


def hnp_scores(traj_xy, packages, cands, cur, onboard, U, synth, G, gzones, t, n, beta=45.0, gamma_geo=1.5, gamma_dl=120.0):
    cpos = traj_xy[cur]
    dists = {j: max(1e-6, dist_2d(*cpos, *traj_xy[j])) for j in cands}
    dmin = min(dists.values())
    scores = {}
    for j in cands:
        tp, rid = node_role(j, n)
        if rid < 0:
            continue
        pkg = packages[rid]
        d = dists[j]
        dl = gamma_dl * pkg.priority / max(1.0, pkg.deadline - t) if tp == "D" else 0
        geo = gamma_geo * geo_penalty(*cpos, *traj_xy[j], gzones)
        blk = beta * blocks_future(rid, onboard, U, synth, packages, G, n) if tp == "D" else 0
        scores[j] = 0.55 * (dmin / d) + 0.45 * pkg.weight + blk + dl - geo
    return scores
