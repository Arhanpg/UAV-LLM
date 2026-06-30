# UAV-LLM — Real-World Semantic Drone Delivery System

> 3D interactive UAV mission planner using real Bengaluru GPS coordinates, MPDD + HNP algorithms, and Ollama LLM (GLM4) for natural language mission control.

---

## 🚀 Features

- **Real-world map** — OpenStreetMap tiles (Leaflet), real Bengaluru GPS coordinates
- **3D altitude planning** — Drone adjusts height based on building heights along route
- **Full algorithm suite** from both papers:
  - `MPDD` — Minimizing Package Delivery Distance (greedy + TSP refinement)
  - `HNP` — Hybrid Neural Planner with semantic constraint synthesis
  - `HNP-NoVerify`, `HNP-NoCompat`, `HNP-NoRefine` — Ablation variants
  - `NN-PDP` — Nearest-neighbour baseline
- **Commodity compatibility graph** (Gc) with safety constraints
- **SMT-style verification** of LLM constraint synthesis
- **Natural language control** — Give drone instructions mid-flight or at mission start
- **Ollama GLM4** runs locally on your RTX 3050 GPU
- **Live algo transparency** — See which algo step is running, params, scoring
- **Dynamic replanning** on disruption events

---

## ⚙️ Setup

### 1. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 2. Install Ollama + pull GLM4
```bash
# Install Ollama: https://ollama.com/download
ollama pull glm4
# Or try: ollama pull glm4:9b  (smaller, fits RTX 3050 4GB)
```

### 3. Run
```bash
python app.py
# Open: http://localhost:8000
```

---

## 🗺️ Using Real Locations

Default depot: **SDM Hospital, Bengaluru**  
Example mission: SDM Hospital → Urban Oasis Mall → Manipal Hospital → back to SDM

You can enter any start/end in the UI or use natural language:
> *"Pick up insulin from SDM Hospital, deliver to Manipal Hospital before 14:00, then collect electronics from Whitefield IT Park and bring back"*

---

## 📐 Math Algorithms Implemented

| Symbol | Description | Reference |
|--------|-------------|----------|
| Ψ(rᵢ) = ⟨κᵢ,τᵢ,ρᵢ,σᵢ⟩ | Semantic constraint synthesis | Eq 1 |
| Gc = (K, Ec) | Commodity compatibility graph | Eq 2 |
| Aᵢ induces clique in Gc | Semantic feasibility | Eq 4 |
| J(π) = αdist·dist + αtime·lateness + αnoise·noise + αenergy·energy | Multi-objective cost | Eq 6 |
| yᵢ ≤ W | Payload constraint | Eq 7b |
| fᵢ',j' = α·dmin/dis + (1-α)·δj'/wmax | MPDD fitness | Eq 6 MPDD |
| Trajectory refinement via 2-opt TSP | Phase 2 | Algo 1 |

---

## 🖥️ Architecture

```
┌─────────────────────────────────┐
│  Browser (index.html)           │
│  ├── Leaflet 3D Map (OSM tiles) │
│  ├── Drone Animation            │
│  ├── Algorithm Dashboard        │
│  ├── NL Instruction Panel       │
│  └── Compat Graph Viz           │
└────────────┬────────────────────┘
             │ REST API
┌────────────▼────────────────────┐
│  FastAPI (app.py)               │
│  ├── MPDD + HNP algorithms      │
│  ├── SMT-style verifier         │
│  ├── Altitude planner           │
│  └── Ollama GLM4 bridge         │
└────────────┬────────────────────┘
             │
┌────────────▼────────────────────┐
│  Ollama (local GPU — RTX 3050)  │
│  Model: GLM4 / GLM4:9b          │
└─────────────────────────────────┘
```

---

## 📁 File Structure

```
UAV-LLM/
├── app.py              # FastAPI backend — all algorithms
├── index.html          # Full 3D UI (Leaflet + Three.js + Charts)
├── requirements.txt
├── README.md
└── semantic_uav_delivery_stress_final.ipynb  # Original math notebook
```
