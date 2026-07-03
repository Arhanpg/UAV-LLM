"""Phase 0 smoke tests — verify modular imports and API wiring."""

from fastapi.testclient import TestClient

from app.algorithms.compat_graph import build_compat, clique_ok
from app.algorithms.mpdd import mpdd_scores
from app.config import CLASSES, OLLAMA_MODEL
from app.geo.locations import load_locations
from app.main import app


def test_imports_and_config():
    assert len(CLASSES) == 7
    assert OLLAMA_MODEL  # configured via env / default
    locs = load_locations()
    assert len(locs) >= 12


def test_compat_graph():
    G = build_compat(0.25, 42)
    assert clique_ok(["PHARMA", "FOOD"], G) is True
    assert clique_ok(["FLAMMABLE", "OXIDIZER"], G) is False


def test_health_endpoint():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["city"] == "Dharwad-Hubli, Karnataka"


def test_locations_endpoint():
    client = TestClient(app)
    r = client.get("/api/locations")
    assert r.status_code == 200
    assert len(r.json()["locations"]) >= 12
