"""Phase 2 trajectory refinement — source-anchored 2-opt (ported from monolith)."""

from app.algorithms.cost import evaluate
from app.algorithms.routing import node_role


def refine(packages, traj_xy, route, synth, G, W, gzones, max_passes=4):
    best = route[:]
    n = len(packages)

    def pick_pos(rt):
        return [i for i, nd in enumerate(rt) if node_role(nd, n)[0] == "P"]

    for _ in range(max_passes):
        improved = False
        anchors = [0] + pick_pos(best) + [len(best) - 1]
        for ai in range(len(anchors) - 1):
            lo, hi = anchors[ai], anchors[ai + 1]
            if hi - lo <= 3:
                continue
            seg = best[lo + 1 : hi]
            dloc = [k for k, nd in enumerate(seg) if node_role(nd, n)[0] == "D"]
            if len(dloc) < 2:
                continue
            base = evaluate(traj_xy, [], packages, best, G, [], [], synth, W)["dist"]
            for xi in range(len(dloc)):
                for yi in range(xi + 1, len(dloc)):
                    cand = best[:]
                    ix, iy = lo + 1 + dloc[xi], lo + 1 + dloc[yi]
                    cand[ix], cand[iy] = cand[iy], cand[ix]
                    m = evaluate(traj_xy, [], packages, cand, G, [], [], synth, W)
                    if m["dist"] < base - 1e-9 and m["pv"] == 0 and m["rv"] == 0:
                        best = cand
                        improved = True
                        break
                if improved:
                    break
            if improved:
                break
        if not improved:
            break
    return best
