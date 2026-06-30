import pytest
import time
import numpy as np

from app.algorithms.mpdd import mpdd_fitness_score, compute_delta, node_role
from app.algorithms.tsp_refine import mst_preorder_tsp, refine
from tests.test_mpdd_paper_example import MockRequest

def test_complexity_growth():
    # test Phase 2 ≈ O(m'^3)
    # We will measure the time of tsp_refine on random sets of locations.
    def setup_fake_route(m_prime):
        packages = [MockRequest(i, i+1, i+1+m_prime, 1.0) for i in range(m_prime)]
        # coords
        np.random.seed(42)
        coords = np.random.rand(2 * m_prime + 2, 2) * 100
        route = [0] + list(range(1, m_prime + 1)) + list(range(m_prime + 1, 2 * m_prime + 1)) + [2 * m_prime + 1]
        return packages, coords, route

    times = []
    sizes = [10, 20, 40] # 80 is too slow for typical tests, 40 is enough to see growth trend
    
    # We mock evaluate to just return dist so it's fast
    import app.algorithms.tsp_refine as tsp
    original_evaluate = tsp.evaluate
    
    def fake_evaluate(traj_xy, _c, _p, rt, _g, _z, _n, _s, _w):
        import math
        d = sum(math.hypot(traj_xy[rt[i]][0]-traj_xy[rt[i+1]][0], traj_xy[rt[i]][1]-traj_xy[rt[i+1]][1]) for i in range(len(rt)-1))
        return {"dist": d, "pv": 0, "rv": 0, "cv": 0}
        
    tsp.evaluate = fake_evaluate
    
    try:
        for m in sizes:
            pkgs, coords, route = setup_fake_route(m)
            t0 = time.perf_counter()
            refine(pkgs, coords, route, None, None, 1000.0, None)
            t1 = time.perf_counter()
            times.append(t1 - t0)
            
        # O(m^3) check: (40/20)^3 = 8. If polynomial, growth ratio should be bounded
        ratio_20_10 = times[1] / max(times[0], 1e-6)
        ratio_40_20 = times[2] / max(times[1], 1e-6)
        
        # It shouldn't be exponential (like 2^10 = 1024x)
        assert ratio_20_10 < 25 # very loose bounds to avoid flakiness, just ensuring not exponential
        assert ratio_40_20 < 25
    finally:
        tsp.evaluate = original_evaluate

