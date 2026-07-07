"""Phase 1 complexity sanity checks.

Phase 2 (Algorithm 1) is O((m')^3): O(m') outer iterations × O((m')^2) MST-TSP
step. We verify empirically that refinement runtime grows polynomially, not
exponentially, across m' ∈ {10, 20, 40}, and that the MST-preorder TSP keeps its
fixed start/end contract.
"""

import time

import app.algorithms.tsp_refine as tsp
import numpy as np
from app.algorithms.tsp_refine import mst_preorder_tsp, refine


class MockPkg:
    def __init__(self, idx, pickup_loc, delivery_loc, weight):
        self.idx = idx
        self.pickup_loc = pickup_loc
        self.delivery_loc = delivery_loc
        self.weight = weight


def _fake_route(m):
    packages = [MockPkg(i, i + 1, i + 1 + m, 1.0) for i in range(m)]
    rng = np.random.default_rng(42)
    coords = [tuple(p) for p in (rng.random((2 * m + 2, 2)) * 1000)]
    route = [0] + list(range(1, m + 1)) + list(range(m + 1, 2 * m + 1)) + [2 * m + 1]
    return packages, coords, route


def test_mst_preorder_fixed_endpoints():
    coords = [(0, 0), (10, 0), (10, 10), (0, 10), (5, 5)]
    nodes = [0, 1, 2, 3, 4]
    order = mst_preorder_tsp(nodes, coords)
    assert order[0] == 0 and order[-1] == 4
    assert sorted(order) == sorted(nodes)  # permutation, no drops/dupes


def test_refinement_polynomial_growth():
    # Fast distance-only evaluate so we isolate the control-flow/TSP cost.
    orig = tsp.evaluate

    def fake_evaluate(traj_xy, _c, _p, rt, _g, _z, _n, _s, _w):
        import math

        d = sum(
            math.hypot(traj_xy[rt[i]][0] - traj_xy[rt[i + 1]][0], traj_xy[rt[i]][1] - traj_xy[rt[i + 1]][1])
            for i in range(len(rt) - 1)
        )
        return {"dist": d, "pv": 0, "rv": 0, "cv": 0}

    tsp.evaluate = fake_evaluate
    try:
        times = []
        for m in (10, 20, 40):
            pkgs, coords, route = _fake_route(m)
            t0 = time.perf_counter()
            out = refine(pkgs, coords, route, None, None, 1e9, None)
            times.append(time.perf_counter() - t0)
            assert out[0] == 0 and out[-1] == 2 * m + 1  # depot start/end preserved
            assert sorted(out) == sorted(route)  # still a valid permutation
        # Doubling m' should stay well below an exponential blow-up.
        r1 = times[1] / max(times[0], 1e-6)
        r2 = times[2] / max(times[1], 1e-6)
        assert r1 < 40 and r2 < 40
    finally:
        tsp.evaluate = orig
