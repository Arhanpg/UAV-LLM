"""Phase 3 — Z3 SMT verifier tests."""

from app.verify.smt_verifier import discrepancy, verify_psi, verify_route


class MockPkg:
    def __init__(self, idx, weight, kappa, deadline=1e9):
        self.idx = idx
        self.weight = weight
        self.kappa = kappa
        self.deadline = deadline


def _all_compatible(classes):
    return {(a, b): True for a in classes for b in classes}


# ---- verify_psi -------------------------------------------------------------
def test_psi_valid_pharma():
    r = verify_psi({"kappa": "PHARMA", "temp_min": 2.0, "temp_max": 8.0, "deadline_minutes": 120})
    assert r["ok"] is True


def test_psi_empty_envelope_fails():
    r = verify_psi({"kappa": "PHARMA", "temp_min": 8.0, "temp_max": 2.0})
    assert r["ok"] is False and r["checks"]["temp_envelope"] is False


def test_psi_nonpositive_deadline_fails():
    r = verify_psi({"kappa": "FOOD", "temp_min": 0.0, "temp_max": 10.0, "deadline_minutes": 0})
    assert r["ok"] is False and r["checks"]["deadline"] is False


def test_psi_unknown_class_fails():
    r = verify_psi({"kappa": "PLUTONIUM", "temp_min": 0.0, "temp_max": 10.0})
    assert r["ok"] is False and r["checks"]["class"] is False


def test_psi_unresolved_zone_fails_when_zones_known():
    r = verify_psi(
        {"kappa": "PHARMA", "temp_min": 2.0, "temp_max": 8.0, "prohibited_zones": ["Sector Z"]},
        known_zones=["residential", "airport"],
    )
    assert r["ok"] is False and r["checks"]["zones"] is False


# ---- verify_route -----------------------------------------------------------
def test_route_feasible():
    pkgs = [MockPkg(0, 1.0, "PHARMA"), MockPkg(1, 1.0, "FOOD")]
    G = _all_compatible(["PHARMA", "FOOD"])
    route = [0, 1, 3, 2, 4, 5]  # pickup0, deliver0, pickup1, deliver1
    synth = {0: "PHARMA", 1: "FOOD"}
    r = verify_route(route, pkgs, synth, G, W=10.0)
    assert r["ok"] is True


def test_route_payload_violation():
    pkgs = [MockPkg(0, 6.0, "GENERAL"), MockPkg(1, 6.0, "GENERAL")]
    G = _all_compatible(["GENERAL"])
    route = [0, 1, 2, 3, 4, 5]  # both picked up before any delivery -> 12kg > W
    synth = {0: "GENERAL", 1: "GENERAL"}
    r = verify_route(route, pkgs, synth, G, W=10.0)
    assert r["payload_ok"] is False and r["ok"] is False


def test_route_precedence_violation():
    pkgs = [MockPkg(0, 1.0, "GENERAL")]
    G = _all_compatible(["GENERAL"])
    route = [0, 2, 1, 3]  # deliver (node 2) before pickup (node 1)
    r = verify_route(route, pkgs, {0: "GENERAL"}, G, W=10.0)
    assert r["precedence_ok"] is False and r["ok"] is False


def test_route_clique_violation():
    pkgs = [MockPkg(0, 1.0, "FLAMMABLE"), MockPkg(1, 1.0, "OXIDIZER")]
    G = _all_compatible(["FLAMMABLE", "OXIDIZER"])
    G[("FLAMMABLE", "OXIDIZER")] = G[("OXIDIZER", "FLAMMABLE")] = False
    route = [0, 1, 2, 3, 4, 5]  # both onboard simultaneously
    synth = {0: "FLAMMABLE", 1: "OXIDIZER"}
    r = verify_route(route, pkgs, synth, G, W=10.0)
    assert r["clique_ok"] is False and r["ok"] is False


def test_discrepancy_detection():
    smt = {"ok": True, "payload_ok": True, "clique_ok": True, "precedence_ok": True}
    assert discrepancy(smt, {"feasible": True}) is None
    msg = discrepancy(smt, {"feasible": False, "cv": 1, "pv": 0, "rv": 0})
    assert msg and "DISCREPANCY" in msg
