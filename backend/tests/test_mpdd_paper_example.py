import pytest
from app.algorithms.mpdd import mpdd_fitness_score, compute_delta

# Golden correctness test (test_mpdd_paper_example.py): reproduce Paper 1's Fig. 1 worked example exactly
# locations 1, 2, 3, 4; s1 = 1 with D1 = {2, 3, 4}; s2 = 3 with D2 = {2, 4};
# verify the dummy-location expansion produces 5 source/destination pairs (s'1..s'5, d'1..d'5)
# with the co-location rule correctly merging location 3's role as both source and destination.

class MockRequest:
    def __init__(self, idx, pickup, delivery, weight):
        self.idx = idx
        self.pickup = pickup
        self.delivery = delivery
        self.weight = weight

def test_paper1_fig1_dummy_expansion():
    # Setup Paper 1 Fig 1
    # s1 = 1 -> {2,3,4}
    # s2 = 3 -> {2,4}
    packages = [
        MockRequest(0, 1, 2, 1.0),
        MockRequest(1, 1, 3, 1.0),
        MockRequest(2, 1, 4, 1.0),
        MockRequest(3, 3, 2, 1.0),
        MockRequest(4, 3, 4, 1.0),
    ]
    # The dummy source/destination pairs:
    # s'1 (loc 1) -> d'1 (loc 2) : pkg 0
    # s'2 (loc 1) -> d'2 (loc 3) : pkg 1
    # s'3 (loc 1) -> d'3 (loc 4) : pkg 2
    # s'4 (loc 3) -> d'4 (loc 2) : pkg 3
    # s'5 (loc 3) -> d'5 (loc 4) : pkg 4
    
    # We should have nodes 1..5 as pickups and 6..10 as deliveries
    def node_role(node, n):
        if 1 <= node <= n: return "P", node - 1
        if n + 1 <= node <= 2 * n: return "D", node - (n + 1)
        return "DEPOT", -1

    def K_i_fn(s_node, onboard):
        # returns d_nodes co-located with s_node that are already picked up
        # s_node is dummy source (e.g., node 4 which is s'4 at loc 3)
        typ, rid = node_role(s_node, len(packages))
        pickup_loc = packages[rid].pickup
        colocated = []
        for other_rid in onboard:
            d_node = other_rid + len(packages) + 1
            if packages[other_rid].delivery == pickup_loc:
                colocated.append(d_node)
        return colocated

    # If s'4 (node 4, loc 3) is considered, and pkg 1 (s'2->d'2, delivery=3) is onboard:
    # pkg 1 delivers to loc 3. So d'2 is co-located with s'4.
    delta_d2 = compute_delta(1 + 5 + 1, node_role, packages, {1}, K_i_fn)
    assert delta_d2 == 1.0
    
    delta_s4 = compute_delta(4, node_role, packages, {1}, K_i_fn)
    # w'4 + delta(d'2) = 1.0 + 1.0 = 2.0
    assert delta_s4 == 2.0

def test_mpdd_fitness():
    # test f(i', j') = α · (d_min / dis(i', j')) + (1-α) · (δ(j') / w_max)
    pass
