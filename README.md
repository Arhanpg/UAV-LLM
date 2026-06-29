# UAV-LLM — Semantic Multi-Commodity UAV Delivery Demo

A full-stack research implementation inspired by the **UAV-LLM** paper and **MPDD** baseline.

## Features
- FastAPI backend with semantic UAV planning APIs
- MPDD baseline + HNP planner + ablations:
  - HNP
  - MPDD
  - NN-PDP
  - HNP-NoVerify
  - HNP-NoCompat
  - HNP-NoRefine
- 3D urban digital-twin UI in Three.js
- Altitude-aware route playback with z-axis building clearance
- Geofencing, noise zones, energy model, wind penalty, battery constraints
- Local Ollama integration for semantic parsing and mid-flight natural-language commands
- Dynamic replanning after disruptions

## Tech Stack
- **Backend:** Python, FastAPI, NumPy, HTTPX
- **Frontend:** HTML, TailwindCSS, Three.js
- **LLM:** Ollama (`glm4` by default, configurable with `OLLAMA_MODEL`)

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate   # or .venv\\Scripts\\activate on Windows
pip install -r requirements.txt
python app.py
```
Then open [http://127.0.0.1:8000](http://127.0.0.1:8000) or [http://localhost:8000](http://localhost:8000)

## Ollama
Run a local model with:
```bash
ollama pull glm4
ollama serve
```
Optional environment variables:
```bash
export OLLAMA_MODEL=glm4
export OLLAMA_URL=http://localhost:11434
```

## API Endpoints
- `POST /api/generate` — generate a full scenario and run planners
- `POST /api/llm/parse` — parse natural-language cargo instruction
- `POST /api/llm/midflight` — classify mid-flight command
- `POST /api/replan` — inject disruption and replan
- `GET /api/compat` — compatibility graph
- `GET /health` — system / Ollama health

## Notes
This project is designed as an interactive research demo, not a production air-traffic or aviation-certified system.
