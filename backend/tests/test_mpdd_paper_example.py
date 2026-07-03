"""Golden regression test — Paper 1, Fig. 1 worked example.

s1 = location 1 with D1 = {2, 3, 4}; s2 = location 3 with D2 = {2, 4}.
After dummy-location splitting there are 5 one-to-one source/destination pairs
(s'1..s'5, d'1..d'5). Location 3 acts as both a source (for s2's packages) and a
destination (for one of s1's packages), so the δ co-location rule (Eq. 2) must
merge the droppable weight at that node. This is the single most important
regression test in the project — if it fails, the core algorithm is broken.
"""

from app.algorithms.mpdd import compute_delta, mpdd_fitness_score, node_role


class MockPkg:
    """Dummy source/destination pair with a one-to-one package."""

    def __init__(self, idx, pickup_loc, delivery_loc, weight):
        self.idx = idx
        self.pickup_loc = pickup_loc
        self.delivery_loc = delivery_loc
        self.weight = weight


# Paper 1 Fig. 1 → 5 packages after dummy splitting.
#   pkg0: s'1 loc1 -> d'1 loc2      pkg3: s'4 loc3 -> d'4 loc2
#   pkg1: s'2 loc1 -> d'2 loc3      pkg4: s'5 loc3 -> d'5 loc4
#   pkg2: s'3 loc1 -> d'3 loc4
PACKAGES = [
    MockPkg(0, 1, 2, 0.6),
    MockPkg(1, 1, 3, 0.7),
    MockPkg(2, 1, 4, 0.8),
    MockPkg(3, 3, 2, 0.6),
    MockPkg(4, 3, 4, 0.7),
]
N = len(PACKAGES)


def K_i(node, onboard):
    """Dummy destinations co-located with source ``node`` already on board."""
    _, rid = node_role(node, N)
    src_loc = PACKAGES[rid].pickup_loc
    return [oid + N + 1 for oid in onboard if PACKAGES[oid].delivery_loc == src_loc]


def test_dummy_expansion_node_encoding():
    # 5 pickup nodes (1..5), 5 delivery nodes (6..10), depot 0 and 11.
    pickups = [node_role(nd, N) for nd in range(1, N + 1)]
    dests = [node_role(nd, N) for nd in range(N + 1, 2 * N + 1)]
    assert [r for r, _ in pickups] == ["P"] * 5
    assert [r for r, _ in dests] == ["D"] * 5
    assert node_role(0, N) == ("DEPOT", -1)
    assert node_role(2 * N + 1, N) == ("DEPOT", -1)
    # Total trajectory length 2m'+2 including depot start/end (Paper 1 §II-A).
    assert 2 * N + 2 == 12


def test_delta_destination_is_own_weight():
    # δ(d'_i) = w'_i  (Eq. 3). d'2 is node 1 + N + 1 = 7 (package 1).
    d2 = N + 1 + 1  # node 7
    assert compute_delta(d2, node_role, PACKAGES, set(), K_i) == 0.7


def test_delta_source_merges_colocated_drop():
    # s'4 (node 4) is at location 3. Package 1 (d'2) delivers to location 3.
    # If package 1 is already onboard, δ(s'4) = w'4 + δ(d'2) = 0.6 + 0.7 = 1.3.
    s4 = 4
    assert abs(compute_delta(s4, node_role, PACKAGES, {1}, K_i) - 1.3) < 1e-9
    # Without package 1 onboard there is nothing to drop → δ = w'4 only.
    assert compute_delta(s4, node_role, PACKAGES, set(), K_i) == 0.6


def test_location3_is_source_and_destination():
    # Location 3 is the delivery of pkg1 (d'2) AND the pickup of pkg3, pkg4.
    dest_pkgs = [p.idx for p in PACKAGES if p.delivery_loc == 3]
    src_pkgs = [p.idx for p in PACKAGES if p.pickup_loc == 3]
    assert dest_pkgs == [1]
    assert src_pkgs == [3, 4]


def test_fitness_equation():
    # f = α·(d_min/dis) + (1-α)·(δ/w_max) with α = 0.7.
    f = mpdd_fitness_score(dmin=10.0, dist_ij=10.0, delta_j=2.0, wmax=2.0, alpha=0.7)
    assert abs(f - 1.0) < 1e-9
    # Closer + heavier candidate scores higher than a far, light one.
    near = mpdd_fitness_score(5.0, 5.0, 2.0, 2.0)
    far = mpdd_fitness_score(5.0, 50.0, 0.5, 2.0)
    assert near > far
