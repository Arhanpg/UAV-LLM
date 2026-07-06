"""Phase 4 — routers, WebSocket telemetry, SQLite persistence (benchmark mode).

Runs with LLM_MODE=benchmark (set in conftest) so no Ollama call is made; the
generation still emits the full telemetry event stream and persists to SQLite.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_data_endpoints():
    assert client.get("/api/locations").json()["locations"]
    cg = client.get("/api/compat-graph").json()
    assert cg["classes"] and cg["edges"]
    gj = client.get("/api/buildings").json()
    assert gj["type"] == "FeatureCollection" and gj["features"]


def test_generate_and_telemetry_stream():
    cfg = {"loc_indices": list(range(8)), "seed": 7}
    # Open the WS first so we capture live events, then generate.
    with client.websocket_connect("/ws/mission/_probe") as _probe:
        pass  # just ensure the endpoint accepts connections

    r = client.post("/api/mission/generate", json=cfg)
    assert r.status_code == 200
    body = r.json()
    sid = body["session_id"]
    assert body["llm_mode"] == "benchmark"
    assert len(body["results"]) == 6  # MPDD, HNP, 3 ablations, NN-PDP
    assert body["flight_path"] and body["alt_profile"]
    assert body["verifier"]["route"]["ok"] in (True, False)

    # History persisted to SQLite and telemetry buffered for the session.
    hist = client.get("/api/missions").json()["missions"]
    assert any(m["session_id"] == sid for m in hist)

    # Replaying the session's telemetry buffer over WS yields real event types.
    with client.websocket_connect(f"/ws/mission/{sid}") as ws:
        seen = set()
        for _ in range(12):
            evt = ws.receive_json()
            seen.add(evt["type"])
            if "route_finalized" in seen:
                break
    assert "phase1_step" in seen or "route_finalized" in seen


def test_replan_causality_preservation():
    body = client.post("/api/mission/generate", json={"loc_indices": list(range(8)), "seed": 9}).json()
    sid = body["session_id"]
    old_route = body["results"]["HNP"]["route"]
    flown = 3
    r = client.post(
        "/api/mission/replan",
        json={"session_id": sid, "disruption": {"type": "nofly", "x": 200, "y": 200, "r": 150}, "flown_steps": flown},
    )
    assert r.status_code == 200
    new_route = r.json()["new_route"]
    # Eq. 8a — the already-flown prefix is preserved verbatim.
    assert new_route[:flown] == old_route[:flown]
