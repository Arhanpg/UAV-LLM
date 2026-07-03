"""Central configuration — single source for tunables and env overrides."""

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BACKEND_DIR / "data"

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", os.getenv("OLLAMA_URL", "http://localhost:11434"))
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:4b")
LLM_MODE = os.getenv("LLM_MODE", "live").lower()

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'data' / 'uav_llm.db'}")

CLASSES = ["PHARMA", "FOOD", "ELECTRONICS", "FLAMMABLE", "OXIDIZER", "CRYOGENIC", "GENERAL"]
HAZARD_CLASSES = {"FLAMMABLE", "OXIDIZER", "CRYOGENIC"}
FIXED_INCOMPAT = [
    ("FLAMMABLE", "OXIDIZER"),
    ("CRYOGENIC", "ELECTRONICS"),
    ("FLAMMABLE", "PHARMA"),
    ("OXIDIZER", "PHARMA"),
    ("CRYOGENIC", "FOOD"),
    ("FLAMMABLE", "FOOD"),
    ("OXIDIZER", "FOOD"),
]

PENALTIES = {
    "compat": 220.0,
    "geo": 160.0,
    "payload": 300.0,
    "precedence": 220.0,
    "missed": 600.0,
}
ALPHA_OBJ = {"distance": 1.0, "lateness": 1.8, "noise": 0.55, "energy": 0.08}
MPDD_ALPHA = 0.7

# Commodity physical properties (Paper 2 Eq. 2, verifier structural checks).
TEMP_ENVELOPES = {  # (τ_min, τ_max) °C
    "PHARMA": (2.0, 8.0),
    "FOOD": (0.0, 25.0),
    "ELECTRONICS": (-10.0, 45.0),
    "FLAMMABLE": (-20.0, 40.0),
    "OXIDIZER": (-20.0, 40.0),
    "CRYOGENIC": (-196.0, -50.0),
    "GENERAL": (-40.0, 60.0),
}
HAZARD = {"FLAMMABLE": "FLAMMABLE", "OXIDIZER": "OXIDIZER", "CRYOGENIC": "CRYOGENIC"}
TEMP_SENSITIVE = {"PHARMA", "FOOD", "CRYOGENIC"}

UAV_SPEED = 15.0
ROTOR_K = 0.04
MIN_ALT = 30.0
CLEARANCE = 12.0
EARTH_R = 6371000.0

# Corridor-based altitude planning (Phase 2, spec §8.4)
BUILDINGS_PATH = DATA_DIR / "buildings_dharwad.geojson"
CORRIDOR_WIDTH = 15.0       # m — buffer either side of the straight-line path
ALT_SAFETY_MARGIN = 15.0    # m — clearance above the tallest building in corridor
MAX_CEILING = 120.0         # m — max operational ceiling (regulatory-style clamp)
VERTICAL_SPEED = 3.0        # m/s — climb/descent rate limit (no z teleporting)
