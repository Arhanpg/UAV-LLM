# UAV-LLM — Semantic Multi-Commodity UAV Delivery

A locally-hosted, GPU-accelerated, **real-3D**, **LLM-driven** UAV mission-planning
and simulation platform. It productionizes two research papers into one auditable
"glass-box" system over the real **Dharwad–Hubli, Karnataka** region:

- **Paper 1 — MPDD** (Chen, Sheu, Bhat, *IEEE WCNC 2025*): greedy multi-commodity
  pickup-and-delivery trajectory construction + MST-preorder TSP refinement,
  implemented exactly per its equations (Eq. 2–7, Algorithm 1) and `O(m'³)` bound.
- **Paper 2 — HNP** (semantic extension): natural-language constraint synthesis Ψ
  via a **real local LLM**, a **Z3** SMT verifier `V`, the commodity compatibility
  graph `Gc`, the multi-objective cost `J(π)`, and causality-preserving dynamic
  replanning under disruption.

Everything the planner decides is streamed live to the UI — per-step fitness
equations with real numbers, the LLM's raw prompt/response/parsed JSON, and the
verifier's accept/reject trace.

> Region: **Dharwad–Hubli**. Backend: **FastAPI**. 3D: **Three.js / React Three
> Fiber** with real OSM building footprints. No map tokens, runs offline.

---

## Architecture

```
backend/   FastAPI + Uvicorn · algorithms · Ollama LLM · Z3 verifier · SQLite · WS telemetry
frontend/  React 18 + TypeScript + Vite · React Three Fiber 3D scene · Zustand · Recharts
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the system + sequence
diagrams and [`docs/MATH_REFERENCE.md`](docs/MATH_REFERENCE.md) for the exact
equation → file/function mapping.

---

## Local LLM model

The LLM runs **locally via Ollama** on your GPU. The model name is a single config
value (`OLLAMA_MODEL`) — never hardcoded. Pick by VRAM (auto-detect with
`python -m scripts.detect_gpu_model`):

| Detected VRAM | Model | Approx. size (Q4) |
|---|---|---|
| ~4 GB (laptop RTX 3050) | `qwen3:4b` *(default)* | ~2.5 GB |
| ~6 GB | `qwen3:4b` / `qwen3:8b` | 2.5–5 GB |
| ~8 GB (desktop RTX 3050) | `qwen3:8b` / `llama3.1:8b` | ~5 GB |
| No GPU | `phi4-mini` (CPU) | ~2.3 GB |

> ⚠️ **GLM-5.2 is not usable locally** — it is a ~744B-parameter cloud model; the
> only Ollama tag (`glm-5.2:cloud`) proxies to Z.ai's datacenter and would defeat
> the "runs privately on my GPU" goal. This project uses `qwen3:4b` by default.

---

## Setup

### Prerequisites
- Python 3.11+, Node 20+
- [Ollama](https://ollama.com) running locally (`ollama serve`)

### 1. Pull the model
```bash
ollama pull qwen3:4b
```

### 2. Backend
```bash
cd backend
pip install -r requirements.txt
cp ../.env.example .env          # optional: tweak OLLAMA_MODEL / LLM_MODE
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend
```bash
cd frontend
npm install
npm run dev                       # http://localhost:5173
```

Open http://localhost:5173 and click **Generate Mission**. Watch `ollama ps` — you
will see active inference for every Ψ synthesis and NL instruction (live mode is
the default; there is **no** fake-LLM fallback in live mode).

### One-command (Docker)
```bash
docker compose up --build         # backend :8000, frontend :5173
```
Ollama stays on the host (consumer GPU passthrough into containers is unreliable);
the backend reaches it at `host.docker.internal:11434`.

---

## LLM modes

| `LLM_MODE` | Behaviour |
|---|---|
| `live` *(default)* | Every Ψ synthesis + NL instruction calls the real local LLM, validated against a Pydantic schema; on invalid output it retries once, then falls back to a **clearly-labeled** rule-based heuristic (never silently). |
| `benchmark` | Reproduces the notebook's stochastic noise-injection model for regenerating the Monte-Carlo ablation plots. Used by CI. Never the interactive default. |

---

## The six algorithms

`MPDD`, `HNP`, `HNP-NoVerify`, `HNP-NoCompat`, `HNP-NoRefine`, `NN-PDP` all run per
mission and are compared in the **Compare** dashboard (distance, cost, violations,
runtime).

## Real 3D

- Real OSM building footprints (`backend/data/buildings_dharwad.geojson`) extruded
  to real heights in Three.js — refresh them with `python -m scripts.fetch_buildings`.
- The drone **climbs and descends** on the z-axis via a corridor-clearance altitude
  planner (tallest building in a buffered corridor + safety margin, ceiling-clamped,
  vertical-speed rate-limited so it never teleports). A live altitude sparkline sits
  in the HUD.

## Glass box

The **Glass Box** tab streams live telemetry over `WS /ws/mission/{id}`:
`phase1_step` (candidate fitness with substituted numbers), `phase2_*` (MST + refine),
`llm_prompt_sent` / `llm_response_received`, `psi_synthesis_result`,
`smt_verify_result`, `route_finalized`, and the replan lifecycle. A verifier
**discrepancy** between Z3 and the heuristic's own bookkeeping is surfaced, never
hidden.

## Disruption & replanning

The **Disrupt** tab injects a preset or free-text disruption (e.g. *"sudden
thunderstorm over Sector Gamma"*). Replanning preserves the already-flown prefix
(causality, Eq. 8a) and continues from the drone's current position; the LLM can
emit `SPLIT_DELIVERY` for mission-topology restructuring.

---

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/mission/generate` | Plan a mission (all 6 algorithms + 3D flight path) |
| POST | `/api/mission/replan` | Causality-preserving replan under disruption |
| POST | `/api/llm/instruction` | Pre-flight / mid-flight NL → structured action list |
| GET | `/api/locations` `/api/buildings` `/api/compat-graph` | Static/derived data |
| GET | `/api/missions` `/api/mission/{id}` | Persisted history |
| WS | `/ws/mission/{id}` | Live glass-box telemetry |

---

## Repository layout

```
UAV-LLM/
├── backend/
│   ├── app/            # FastAPI app, algorithms, llm, verify, geo, ws, routers, models
│   ├── data/           # locations_dharwad.json, buildings_dharwad.geojson
│   ├── scripts/        # fetch_buildings.py, detect_gpu_model.py
│   └── tests/          # pytest suite
├── frontend/           # React + R3F app (scene/, panels/, store/, ws/, api/)
├── notebooks/          # original Monte-Carlo research notebook (unmodified)
├── docs/               # ARCHITECTURE.md, MATH_REFERENCE.md
├── docker-compose.yml  ·  .github/workflows/ci.yml  ·  .env.example
```

---

## Tests

```bash
cd backend && pytest -q          # algorithms, Z3 verifier, telemetry, replan (benchmark mode)
cd frontend && npm run test      # projection / world-transform
```

The golden regression [`test_mpdd_paper_example.py`](backend/tests/test_mpdd_paper_example.py)
reproduces Paper 1 Fig. 1's dummy-location expansion (5 pairs, location 3 acting as
both source and destination). CI (`.github/workflows/ci.yml`) runs ruff + pytest and
eslint + typecheck + build + vitest on every push/PR.

---

## Research notebook

`notebooks/semantic_uav_delivery_stress_final.ipynb` is kept unmodified as the
original pure-math Monte-Carlo benchmark; `LLM_MODE=benchmark` reproduces its model.
