# Architecture

UAV-LLM is a two-service application: a **FastAPI** backend that runs the
research algorithms, the local LLM, and the Z3 verifier, and a **React + Three.js**
frontend that renders the mission in 3D and streams the "glass-box" telemetry.

## System diagram

```mermaid
flowchart TB
    subgraph Browser["Frontend — React 18 + R3F (Vite, :5173)"]
        UI[App.tsx / Sidebar tabs]
        Scene[CityScene · Buildings · Drone · FlightPath · NodeMarkers]
        Panels[MissionBuilder · AlgorithmInspector · ComparisonDashboard · CompatGraphView · NLInstruction · Disruption]
        Store[(Zustand missionStore)]
        WS[useTelemetry WS hook]
        UI --> Store
        Scene --> Store
        Panels --> Store
        WS --> Store
    end

    subgraph Backend["Backend — FastAPI + Uvicorn (:8000)"]
        Routers[routers: mission · llm · data]
        MS[services/mission_service]
        subgraph Algo["algorithms/"]
            MPDD[mpdd.py Eq.2-7]
            TSP[tsp_refine.py Alg.1]
            HNP[hnp.py]
            COST[cost.py Eq.5-6]
            COMPAT[compat_graph.py Eq.2-4]
            ALT[altitude.py corridor clearance]
            NN[nn_baseline.py]
        end
        LLM[llm: ollama_client · psi_synthesis · nl_mission_parser]
        VERIFY[verify/smt_verifier.py Z3]
        GEO[geo: projection · buildings · locations]
        BUS[ws/telemetry event bus]
        DB[(SQLite via SQLModel)]
        Routers --> MS
        MS --> Algo
        MS --> LLM
        MS --> VERIFY
        MS --> GEO
        MS --> BUS
        MS --> DB
    end

    Ollama[[Ollama on host GPU\nqwen3:4b · :11434]]

    UI -- REST /api/mission/* /api/llm/* /api/* --> Routers
    WS -- WS /ws/mission/{sid} --> BUS
    BUS -- events --> WS
    LLM -- /api/chat structured JSON --> Ollama
```

## Request lifecycle (generate a mission)

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant API as /api/mission/generate
    participant MS as mission_service
    participant LLM as psi_synthesis (Ollama)
    participant V as Z3 verifier
    participant ALG as run_all_algos
    participant BUS as telemetry bus

    FE->>API: POST GenConfig
    API->>MS: generate_mission(cfg)
    MS->>BUS: session_start
    loop each package
        MS->>LLM: Ψ(request) → ⟨κ,τ,ρ,σ⟩
        LLM-->>MS: structured JSON (validated)
        MS->>V: verify_psi (Z3 structural)
        MS->>BUS: llm_prompt_sent / llm_response_received / psi_synthesis_result / smt_verify_result
    end
    MS->>ALG: MPDD, HNP, 3 ablations, NN-PDP
    ALG->>BUS: phase1_step · phase2_* · route_finalized
    MS->>V: verify_route (independent Z3 re-check) + discrepancy()
    MS->>MS: build 3D flight path + rate-limited altitude profile
    MS->>DB: persist mission
    API-->>FE: session_id + results + flight_path + verifier
    FE->>BUS: open WS, replay + live telemetry
```

## Key decisions

- **Ollama on the host, not in Docker.** Consumer GPU passthrough into containers
  is unreliable on Windows/WSL, so the backend container reaches the host model
  server at `host.docker.internal:11434`.
- **Deterministic missions.** A mission is fully determined by its `GenConfig`
  (seeded world generation), so persistence stores the config and a summary and
  rehydrates the full world after a restart by re-running generation.
- **Telemetry is decoupled.** Algorithm/LLM/verifier code emits via a
  context-scoped `emit()` that is a no-op when no session is active (e.g. in unit
  tests), so the math modules stay auditable against the papers.
- **Token-free 3D.** Building geometry is committed OSM GeoJSON extruded in plain
  Three.js — no Mapbox/Cesium key required; the app runs fully offline.
