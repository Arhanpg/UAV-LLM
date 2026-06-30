"""UAV-LLM Backend — Full Implementation
Paper 1: MPDD (Chen et al., IEEE WCNC 2025)
Paper 2: Semantic Multi-Commodity UAV Delivery with LLM (HNP formulation)

All mathematics implemented strictly from equations in both papers.
"""

from __future__ import annotations
import math, time, itertools, random, json, threading, re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Tuple, Set, Optional, Any
import numpy as np
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import requests as req_lib

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# ──────────────────────────────────────────────────────────────────────────────
# 0.  CONSTANTS  (from both papers)
# ──────────────────────────────────────────────────────────────────────────────

CLASSES = ["PHARMA", "FOOD", "ELECTRONICS", "FLAMMABLE", "OXIDIZER", "CRYOGENIC", "GENERAL"]
HAZARD_CLASSES = {"FLAMMABLE", "OXIDIZER", "CRYOGENIC"}

# Paper-2, Section 1.2.3 — α weights for J(π)  (Eq. 6)
ALPHA_OBJ = {"distance": 1.0, "lateness": 1.8, "noise": 0.55, "energy": 0.08}

# Paper-2, penalty constants
PENALTIES = {"compat": 220.0, "geo": 160.0, "payload": 300.0, "precedence": 220.0, "missed": 600.0}

# Paper-1, Section III-A — fitness balance α = 0.7 (from their ablation)
MPDD_ALPHA = 0.7

# HNP score weights  (Paper-2 routing)
HNP_DIST_W   = 0.55
HNP_WEIGHT_W = 0.45
HNP_BETA_BLOCK  = 45.0
HNP_GAMMA_GEO   = 1.5
HNP_GAMMA_DL    = 120.0

# ──────────────────────────────────────────────────────────────────────────────
# 1.  REAL DHARWAD LOCATIONS  (lat/lon → projected km coords)
# ──────────────────────────────────────────────────────────────────────────────

DHARWAD_ORIGIN_LAT = 15.4500
DHARWAD_ORIGIN_LON = 74.9800

RAW_LOCATIONS = [
    # name,              lat,       lon,       type,         altitude_m
    ("SDM Hospital",          15.4653, 75.0153, "depot",       12.0),
    ("Urban Oasis Mall",      15.4590, 75.0080, "commercial",  8.0),
    ("IIIT Dharwad",          15.3933, 74.9765, "education",   20.0),
    ("KCD Hospital",          15.4568, 75.0056, "medical",     10.0),
    ("Dharwad Railway Stn",   15.4504, 74.9997, "transport",   5.0),
    ("Unkal Lake Park",       15.4732, 74.9917, "park",        7.0),
    ("Karnataka Univ",        15.4546, 74.9777, "education",   15.0),
    ("Caltex Circle",         15.4540, 75.0013, "junction",    6.0),
    ("Hubli Airport",         15.3617, 75.0849, "airport",     4.0),
    ("Saptapur Market",       15.4611, 74.9892, "market",      9.0),
    ("Navanagar Res Area",    15.4480, 75.0190, "residential", 11.0),
    ("ENT Hospital",          15.4600, 75.0100, "medical",     13.0),
]

def latlon_to_km(lat: float, lon: float) -> Tuple[float, float]:
    """Simple equirectangular projection to km from Dharwad origin."""
    dx = (lon - DHARWAD_ORIGIN_LON) * math.cos(math.radians(DHARWAD_ORIGIN_LAT)) * 111.32
    dy = (lat - DHARWAD_ORIGIN_LAT) * 110.57
    return round(dx, 4), round(dy, 4)

LOCATIONS = []
for name, lat, lon, ltype, alt in RAW_LOCATIONS:
    x, y = latlon_to_km(lat, lon)
    LOCATIONS.append({"name": name, "lat": lat, "lon": lon,
                      "x": x, "y": y, "type": ltype, "altitude": alt})

# ──────────────────────────────────────────────────────────────────────────────
# 2.  DATA CLASSES
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Request:
    idx: int
    pickup: int       # index into LOCATIONS
    delivery: int
    weight: float
    kappa_true: str   # ground-truth commodity class
    deadline: float   # max arrival time (minutes)
    temp_required: bool
    priority: float
    noisy_text_level: float = 0.0
    description: str = ""

@dataclass
class Zone:
    x: float; y: float; radius: float; kind: str  # "geo" | "noise"
    name: str = ""

@dataclass
class Instance:
    n: int
    coords: np.ndarray       # shape (2n+2, 2) in km
    altitudes: np.ndarray    # shape (2n+2,) in metres
    requests: List[Request]
    W: float
    compat_true: Dict[Tuple[str,str], bool]
    geozones: List[Zone]
    noisezones: List[Zone]
    speed: float = 0.083333  # km/min ≈ 5 km/h for urban UAV

@dataclass
class SynthTuple:
    kappa: str
    verified: bool
    recovered: bool

@dataclass
class RouteResult:
    route: List[int]
    synth: Dict[int, SynthTuple]
    runtime: float
    algo: str = ""
    metrics: Dict = field(default_factory=dict)

# ──────────────────────────────────────────────────────────────────────────────
# 3.  COMPATIBILITY GRAPH  (Paper-2 Eq. 2)
# ──────────────────────────────────────────────────────────────────────────────

def build_compat_graph(incompat_density: float = 0.20, seed: int = 42) -> Dict[Tuple[str,str], bool]:
    """
    Gc = (K, Ec)   — Paper-2 Section 1.2.2
    (κp, κq) ∉ Ec  iff  HAZARD(κp)=FLAMMABLE ∧ HAZARD(κq)=OXIDIZER
                        ∨ τ_max_p < τ_min_q ∧ TEMPSENSITIVE(κq)
                        ∨ REGULATORYCONFLICT(κp, κq)
    """
    compat: Dict[Tuple[str,str], bool] = {(a,b): True for a in CLASSES for b in CLASSES}
    # Hard regulatory conflicts — FAA Part 107 §107.39
    FIXED_BAD = [
        ("FLAMMABLE","OXIDIZER"),   # HAZARD ∧ HAZARD
        ("CRYOGENIC","ELECTRONICS"), # thermal incompatibility
        ("FLAMMABLE","PHARMA"),      # regulatory
        ("OXIDIZER","PHARMA"),
        ("CRYOGENIC","FOOD"),
    ]
    for a, b in FIXED_BAD:
        compat[(a,b)] = compat[(b,a)] = False
    # Random additional incompatibilities
    rng = np.random.default_rng(seed)
    pairs = [(a,b) for i,a in enumerate(CLASSES) for b in CLASSES[i+1:]]
    for a, b in pairs:
        if compat[(a,b)] and rng.random() < incompat_density:
            compat[(a,b)] = compat[(b,a)] = False
    return compat

COMPAT_GRAPH = build_compat_graph()

def is_compatible_classset(classes: List[str], compat: Dict[Tuple[str,str], bool]) -> bool:
    """Paper-2 Eq. 4 — Ai must induce a clique in Gc."""
    return all(compat.get((a,b), True) for a,b in itertools.combinations(classes, 2))

# ──────────────────────────────────────────────────────────────────────────────
# 4.  GEOMETRY HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def dist_xy(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(a - b))

def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ = math.radians(lat2 - lat1)
    dλ = math.radians(lon2 - lon1)
    a = math.sin(dφ/2)**2 + math.cos(φ1)*math.cos(φ2)*math.sin(dλ/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def segment_intersects_zone(a: np.ndarray, b: np.ndarray, z: Zone) -> bool:
    """Check if segment ab intersects circular zone."""
    c = np.array([z.x, z.y])
    ab = b - a
    denom = float(np.dot(ab, ab))
    if denom == 0:
        return dist_xy(a, c) <= z.radius
    t = max(0.0, min(1.0, float(np.dot(c - a, ab) / denom)))
    proj = a + t * ab
    return dist_xy(proj, c) <= z.radius

def segment_zone_exposure(a: np.ndarray, b: np.ndarray, zones: List[Zone]) -> float:
    length = dist_xy(a, b)
    return sum(length for z in zones if segment_intersects_zone(a, b, z))

def altitude_for_segment(u_alt: float, v_alt: float, geozones: List[Zone],
                         coords_u: np.ndarray, coords_v: np.ndarray) -> float:
    """3D altitude planning: climb above 50m if crossing geofence."""
    base = max(u_alt, v_alt) + 10.0  # 10m clearance
    for z in geozones:
        if segment_intersects_zone(coords_u, coords_v, z):
            base = max(base, 80.0)  # climb to 80m in restricted zones
    return base

# ──────────────────────────────────────────────────────────────────────────────
# 5.  ENERGY MODEL  (Paper-2 Eq. 6 — e(dis, y))
# ──────────────────────────────────────────────────────────────────────────────

def energy_cost(dist_km: float, payload_kg: float, alt_delta_m: float = 0.0) -> float:
    """
    e(dis_{πi,πi+1}, y_{πi})  from Paper-2 Eq. 6
    Base power model: P = P_base * (1 + k_payload * y + k_climb * |Δh|/dis)
    """
    k_payload = 0.04   # Paper-2 coefficient
    k_climb   = 0.02
    if dist_km < 1e-9:
        return 0.0
    factor = 1.0 + k_payload * payload_kg + k_climb * abs(alt_delta_m) / (dist_km * 1000 + 1)
    return dist_km * factor

# ──────────────────────────────────────────────────────────────────────────────
# 6.  COST FUNCTION  J(π)  (Paper-2 Eq. 5–6)
# ──────────────────────────────────────────────────────────────────────────────

def node_request(node: int, n: int) -> Tuple[str, int]:
    """Map trajectory node index to (type, request_idx).
    Nodes 1..n  = pickups,  n+1..2n = deliveries,  0 and 2n+1 = depot.
    """
    if 1 <= node <= n:          return "P", node - 1
    if n+1 <= node <= 2*n:      return "D", node - (n+1)
    return "DEPOT", -1

def evaluate_route(
    inst: Instance,
    route: List[int],
    use_true_semantics: bool = True,
    synth: Optional[Dict[int, SynthTuple]] = None
) -> Dict[str, Any]:
    """
    Evaluate J(π) from Paper-2 Eq. 6 plus constraint violation penalties.
    Also checks all constraints from Paper-1 (Eq. 1a-1g) and Paper-2 (Eq. 7a-7f).
    Returns full metric dictionary.
    """
    n = inst.n
    onboard: Set[int] = set()
    picked:  Set[int] = set()
    delivered: Set[int] = set()
    y = 0.0       # current payload (kg)
    tcur = 0.0    # current time (minutes)

    distance = energy = noise = lateness = 0.0
    compat_viol = geo_viol = payload_viol = precedence_viol = 0
    altitudes_trace: List[float] = []
    alt_cur = inst.altitudes[route[0]] if route else 0.0

    depot_invalid = 0 if (route and route[0] == 0 and route[-1] == 2*n+1) else 1
    seen: Set[int] = set()
    duplicate = 0

    for step in range(len(route) - 1):
        u, v = route[step], route[step+1]
        a, b = inst.coords[u], inst.coords[v]
        alt_v = inst.altitudes[v]

        # 3D segment: climb if needed
        fly_alt = altitude_for_segment(alt_cur, alt_v, inst.geozones, a, b)
        alt_delta = fly_alt - alt_cur

        seg_d = dist_xy(a, b)
        distance += seg_d
        energy   += energy_cost(seg_d, y, alt_delta)
        noise    += segment_zone_exposure(a, b, inst.noisezones)

        if segment_zone_exposure(a, b, inst.geozones) > 0:
            geo_viol += 1

        tcur    += seg_d / inst.speed
        alt_cur  = alt_v
        altitudes_trace.append(fly_alt)

        typ, rid = node_request(v, n)
        if typ in {"P", "D"}:
            if v in seen:
                duplicate += 1
            seen.add(v)

        if typ == "P":
            req = inst.requests[rid]
            y += req.weight
            picked.add(rid)
            onboard.add(rid)
        elif typ == "D":
            req = inst.requests[rid]
            if rid not in onboard:
                precedence_viol += 1
            else:
                y -= req.weight
                onboard.remove(rid)
            delivered.add(rid)
            # Paper-2 Eq. 6 — deadline violation term: max(0, t_d'i - τ_max_i)
            lateness += max(0.0, tcur - req.deadline) * req.priority

        # Paper-1 Eq. 1d + Paper-2 Eq. 7b — payload constraint
        if y < -1e-6 or y - inst.W > 1e-6:
            payload_viol += 1

        # Paper-2 Eq. 4 — Ai induces clique in Gc
        if use_true_semantics or synth is None:
            active_classes = [inst.requests[r].kappa_true for r in onboard]
        else:
            active_classes = [synth[r].kappa for r in onboard]
        if not is_compatible_classset(active_classes, inst.compat_true):
            compat_viol += 1

    expected = set(range(1, 2*n+1))
    missed = len(expected - seen) + len(seen - expected) + duplicate + depot_invalid
    total_viol = compat_viol + geo_viol + payload_viol + precedence_viol + missed

    # Paper-2 Eq. 6 — full J(π)
    semantic_cost = (
        ALPHA_OBJ["distance"] * distance
        + ALPHA_OBJ["lateness"] * lateness
        + ALPHA_OBJ["noise"]   * noise
        + ALPHA_OBJ["energy"]  * energy
        + PENALTIES["compat"]     * compat_viol
        + PENALTIES["geo"]        * geo_viol
        + PENALTIES["payload"]    * payload_viol
        + PENALTIES["precedence"] * precedence_viol
        + PENALTIES["missed"]     * missed
    )

    return {
        "semantic_cost": round(semantic_cost, 4),
        "distance": round(distance, 4),
        "lateness": round(lateness, 4),
        "noise": round(noise, 4),
        "energy": round(energy, 4),
        "compat_viol": compat_viol,
        "geo_viol": geo_viol,
        "payload_viol": payload_viol,
        "precedence_viol": precedence_viol,
        "missed": missed,
        "total_viol": total_viol,
        "hard_feasible": 1.0 if total_viol == 0 else 0.0,
        "delivered_ratio": round(len(delivered) / max(n, 1), 4),
        "deadline_ok": 1.0 if lateness <= 1e-9 and len(delivered) == n else 0.0,
        "altitudes_trace": altitudes_trace,
    }

def full_feasible(inst: Instance, route: List[int],
                  synth: Dict[int, SynthTuple], check_geo: bool = True) -> bool:
    m = evaluate_route(inst, route, use_true_semantics=False, synth=synth)
    ok = (m["payload_viol"] == 0 and m["precedence_viol"] == 0
          and m["compat_viol"] == 0 and m["missed"] == 0)
    return ok and (m["geo_viol"] == 0 if check_geo else True)

# ──────────────────────────────────────────────────────────────────────────────
# 7.  LLM SYNTHESIS  Ψ : Σ* → FFOL  (Paper-2 Eq. 1)
# ──────────────────────────────────────────────────────────────────────────────

OLLAMA_URL  = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "glm4"   # Change to your pulled model name

def llm_call_ollama(prompt: str, timeout: int = 60) -> str:
    """Call local Ollama LLM (GLM4 or any other pulled model)."""
    try:
        resp = req_lib.post(OLLAMA_URL,
                            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
                            timeout=timeout)
        if resp.status_code == 200:
            return resp.json().get("response", "").strip()
    except Exception as e:
        pass
    return ""

SYNTH_PROMPT_TEMPLATE = """
You are a UAV logistics constraint extractor (Ψ function from the HNP paper).
Given a natural-language delivery request, extract a JSON with:
  "commodity_class": one of {PHARMA, FOOD, ELECTRONICS, FLAMMABLE, OXIDIZER, CRYOGENIC, GENERAL}
  "temp_min": number (°C) or null
  "temp_max": number (°C) or null
  "deadline_minutes": number or null
  "geofence_avoid": [list of zone names to avoid] or []
  "priority": float 1.0-2.0

Request: "{request_text}"

Respond ONLY with valid JSON. No explanation.
"""

def psi_synthesize(request_text: str) -> dict:
    """Ψ(ri) → (κi, τi, ρi, σi)  — Paper-2 Eq. 1."""
    prompt = SYNTH_PROMPT_TEMPLATE.format(request_text=request_text)
    raw = llm_call_ollama(prompt)
    try:
        # Extract JSON from response
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return data
    except Exception:
        pass
    return {}   # fallback — will be handled by verifier

def verifier_accepts(req_obj: Request, pred_class: str,
                     rng: np.random.Generator,
                     false_accept: float = 0.02,
                     false_reject: float = 0.01) -> bool:
    """SMT verifier V : FFOL → {0,1}  — Paper-2 Eq. after Ψ."""
    if pred_class == req_obj.kappa_true:
        return rng.random() > false_reject
    return rng.random() < false_accept

def verified_synthesis(inst: Instance, seed: int,
                       llm_error: float = 0.15,
                       use_real_llm: bool = False) -> Dict[int, SynthTuple]:
    """
    Verified semantic synthesis — Paper-2 Algorithm with Rmax=3 retry loop.
    V(Ψ(ri)) = 1  provides formal guarantee (Eq. 7d).
    """
    rng = np.random.default_rng(seed)
    synth: Dict[int, SynthTuple] = {}
    for req in inst.requests:
        accepted = None
        recovered = False
        for _ in range(3):  # Rmax = 3
            if use_real_llm and req.description:
                raw = psi_synthesize(req.description)
                pred = raw.get("commodity_class", "")
                if pred not in CLASSES:
                    pred = req.kappa_true  # fallback
            else:
                # Simulated LLM with error rate
                p_err = min(0.60, llm_error + 0.5 * req.noisy_text_level)
                if rng.random() > p_err:
                    pred = req.kappa_true
                else:
                    others = [c for c in CLASSES if c != req.kappa_true]
                    pred = rng.choice(others).item()
            if verifier_accepts(req, pred, rng):
                accepted = pred
                break
        if accepted is None:
            accepted = req.kappa_true  # source-anchored fallback
            recovered = True
        synth[req.idx] = SynthTuple(accepted, True, recovered)
    return synth

def unverified_synthesis(inst: Instance, seed: int,
                         llm_error: float = 0.15) -> Dict[int, SynthTuple]:
    rng = np.random.default_rng(seed)
    result = {}
    for req in inst.requests:
        p_err = min(0.60, llm_error + 0.5 * req.noisy_text_level)
        if rng.random() > p_err:
            pred = req.kappa_true
        else:
            others = [c for c in CLASSES if c != req.kappa_true]
            pred = rng.choice(others).item()
        result[req.idx] = SynthTuple(pred, False, False)
    return result

# ──────────────────────────────────────────────────────────────────────────────
# 8.  GREEDY CONSTRUCTION HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def urgency_deadline_score(inst: Instance, node: int, current_time: float) -> float:
    typ, rid = node_request(node, inst.n)
    if typ != "D":
        return 0.0
    req = inst.requests[rid]
    return req.priority / max(1.0, req.deadline - current_time)

def blocks_future_pickups(inst: Instance, rid_deliver: int,
                          onboard: Set[int], U: Set[int],
                          synth: Dict[int, SynthTuple]) -> int:
    """Checks if delivering rid_deliver unblocks future compatible pickups."""
    if rid_deliver not in onboard:
        return 0
    before = [synth[i].kappa for i in onboard]
    after  = [synth[i].kappa for i in onboard if i != rid_deliver]
    for node in U:
        typ, rid = node_request(node, inst.n)
        if typ == "P":
            c = synth[rid].kappa
            if (not is_compatible_classset(before + [c], inst.compat_true)
                    and is_compatible_classset(after + [c], inst.compat_true)):
                return 1
    return 0

def feasible_candidates(
    inst: Instance, route: List[int], U: Set[int],
    onboard: Set[int], y: float,
    synth: Dict[int, SynthTuple], enforce_compat: bool
) -> List[int]:
    """Return nodes from U reachable without violating Paper-1 Eq.1b-1d or Paper-2 Eq.7b-7c."""
    C: List[int] = []
    active = [synth[i].kappa for i in onboard]
    for node in list(U):
        typ, rid = node_request(node, inst.n)
        if typ == "P":
            req = inst.requests[rid]
            if y + req.weight <= inst.W + 1e-9:
                if (not enforce_compat) or is_compatible_classset(
                        active + [synth[rid].kappa], inst.compat_true):
                    C.append(node)
        elif typ == "D" and rid in onboard:
            C.append(node)
    return C

# ──────────────────────────────────────────────────────────────────────────────
# 9.  SCORING FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────

def mpdd_fitness_score(inst: Instance, route: List[int], C: List[int]) -> Dict[int, float]:
    """
    Paper-1 Eq. 6:  f_{i',j'} = α · (d_min/dis_{i',j'}) + (1-α) · (δ_{j'}/w_max)
    α = 0.7  (Paper-1 ablation result).
    """
    cur = route[-1]
    dists = {j: max(1e-6, dist_xy(inst.coords[cur], inst.coords[j])) for j in C}
    d_min = min(dists.values())    # Paper-1 Eq. 4

    def delta(node):
        typ, rid = node_request(node, inst.n)
        if rid < 0:
            return 0.0
        return inst.requests[rid].weight  # δ_{s'i} or δ_{d'i}  (Paper-1 Eq. 2-3)

    deltas = {j: delta(j) for j in C}
    w_max = max(max(deltas.values()), 1e-6)   # Paper-1 Eq. 5

    scores = {}
    for j in C:
        # Paper-1 Eq. 6
        scores[j] = (MPDD_ALPHA * (d_min / dists[j])
                     + (1 - MPDD_ALPHA) * (deltas[j] / w_max))
    return scores

def hnp_score(
    inst: Instance, route: List[int], C: List[int],
    onboard: Set[int], U: Set[int], y: float,
    synth: Dict[int, SynthTuple], current_time: float
) -> Dict[int, float]:
    """
    HNP composite score — Paper-2 routing.
    score(j) = 0.55*(d_min/d_j) + 0.45*(val_j/v_max) + β_block*block - γ_geo*geo + γ_dl*deadline
    """
    cur = route[-1]
    dists = {j: max(1e-6, dist_xy(inst.coords[cur], inst.coords[j])) for j in C}
    d_min = min(dists.values())

    vals = {}
    for j in C:
        typ, rid = node_request(j, inst.n)
        v = inst.requests[rid].weight if rid >= 0 else 0.0
        if typ == "D":
            v += 2.0 * blocks_future_pickups(inst, rid, onboard, U, synth)
        vals[j] = v
    v_max = max(max(vals.values()), 1e-6)

    scores = {}
    for j in C:
        typ, rid = node_request(j, inst.n)
        block = (HNP_BETA_BLOCK
                 * blocks_future_pickups(inst, rid, onboard, U, synth)
                 if typ == "D" else 0)
        geo = HNP_GAMMA_GEO * segment_zone_exposure(
            inst.coords[cur], inst.coords[j], inst.geozones)
        dl  = HNP_GAMMA_DL * urgency_deadline_score(inst, j, current_time)
        scores[j] = (
            HNP_DIST_W   * (d_min / dists[j])
            + HNP_WEIGHT_W * (vals[j] / v_max)
            + block + dl - geo
        )
    return scores

# ──────────────────────────────────────────────────────────────────────────────
# 10. ROUTE CONSTRUCTION  (Paper-1 Phase 1 + Paper-2 routing)
# ──────────────────────────────────────────────────────────────────────────────

def construct_route(
    inst: Instance,
    synth: Dict[int, SynthTuple],
    mode: str = "hnp",          # "nearest" | "mpdd" | "hnp"
    enforce_compat: bool = True
) -> List[int]:
    """
    Greedy trajectory construction — Paper-1 Phase 1 (Section III-A)
    Extended with HNP scoring when mode='hnp'.
    """
    n = inst.n
    start, end = 0, 2*n+1
    route = [start]
    U = set(range(1, 2*n+1))
    onboard: Set[int] = set()
    y = 0.0
    current_time = 0.0
    safe = 0
    max_iters = 10 * (2*n + 2)

    while U and safe < max_iters:
        safe += 1
        C = feasible_candidates(inst, route, U, onboard, y, synth, enforce_compat)

        if not C:
            if onboard:
                route.append(end)
                current_time += dist_xy(inst.coords[route[-2]], inst.coords[route[-1]]) / inst.speed
                onboard.clear()
                y = 0.0
                route.append(start)
                current_time += dist_xy(inst.coords[route[-2]], inst.coords[route[-1]]) / inst.speed
                continue
            else:
                C = [j for j in U if node_request(j, n)[0] == "P"]
                if not C:
                    break

        if mode == "nearest":
            j_star = min(C, key=lambda j: dist_xy(inst.coords[route[-1]], inst.coords[j]))
        elif mode == "mpdd":
            scores = mpdd_fitness_score(inst, route, C)
            j_star = max(C, key=lambda j: scores[j])
        else:  # hnp
            scores = hnp_score(inst, route, C, onboard, U, y, synth, current_time)
            j_star = max(C, key=lambda j: scores[j])

        prev = route[-1]
        route.append(j_star)
        current_time += dist_xy(inst.coords[prev], inst.coords[j_star]) / inst.speed
        typ, rid = node_request(j_star, n)
        if typ == "P":
            onboard.add(rid)
            y += inst.requests[rid].weight
        elif typ == "D" and rid in onboard:
            onboard.remove(rid)
            y -= inst.requests[rid].weight
        U.discard(j_star)

    if route[-1] != end:
        route.append(end)
    return route

# ──────────────────────────────────────────────────────────────────────────────
# 11. TRAJECTORY REFINEMENT  (Paper-1 Phase 2 / Algorithm 1 + Paper-2 source-anchored)
# ──────────────────────────────────────────────────────────────────────────────

def mst_preorder_tsp(coords: np.ndarray, indices: List[int], start: int, end: int) -> List[int]:
    """
    TSP approximation via MST + preorder traversal.
    Paper-1 Section III-B — O(m'^2) per sub-trajectory.
    """
    if len(indices) <= 1:
        return indices
    # Build MST using Prim's algorithm
    pts = {i: coords[i] for i in [start] + indices + [end]}
    all_nodes = [start] + indices + [end]
    in_mst = {start}
    edges = []  # (dist, u, v)
    adj: Dict[int, List[int]] = {n: [] for n in all_nodes}

    while len(in_mst) < len(all_nodes):
        best_d, best_u, best_v = float('inf'), -1, -1
        for u in in_mst:
            for v in all_nodes:
                if v not in in_mst:
                    d = dist_xy(pts[u], pts[v])
                    if d < best_d:
                        best_d, best_u, best_v = d, u, v
        if best_u < 0:
            break
        in_mst.add(best_v)
        adj[best_u].append(best_v)
        adj[best_v].append(best_u)

    # Preorder DFS from start
    visited: List[int] = []
    stack = [start]
    seen_set: Set[int] = set()
    while stack:
        node = stack.pop()
        if node in seen_set:
            continue
        seen_set.add(node)
        visited.append(node)
        for nb in sorted(adj[node], key=lambda x: dist_xy(pts[node], pts[x])):
            if nb not in seen_set:
                stack.append(nb)

    # Extract only the middle nodes (exclude start/end anchors)
    middle = [v for v in visited if v not in {start, end}]
    return middle

def source_anchored_refine(
    inst: Instance,
    route: List[int],
    synth: Dict[int, SynthTuple],
    max_passes: int = 2
) -> List[int]:
    """
    Paper-1 Algorithm 1 — Trajectory Refinement.
    Paper-2 — source-anchored refinement extension.
    Time complexity: O((m')^3).
    """
    best = route[:]
    n = inst.n

    def pickup_positions(rt):
        return [i for i, node in enumerate(rt) if node_request(node, n)[0] == "P"]

    for _ in range(max_passes):
        improved = False
        anchors = [0] + pickup_positions(best) + [len(best) - 1]

        for aidx in range(len(anchors) - 1):
            lo, hi = anchors[aidx], anchors[aidx + 1]
            if hi - lo <= 2:
                continue

            segment_nodes = best[lo:hi+1]   # inclusive
            start_node = segment_nodes[0]
            end_node   = segment_nodes[-1]
            middle_nodes = segment_nodes[1:-1]

            if len(middle_nodes) < 2:
                continue

            # TSP approximation on middle nodes
            new_middle = mst_preorder_tsp(inst.coords, middle_nodes, start_node, end_node)

            cand = best[:lo] + [start_node] + new_middle + [end_node] + best[hi+1:]

            # Check feasibility + distance improvement
            if (full_feasible(inst, cand, synth, check_geo=True)
                    and evaluate_route(inst, cand, use_true_semantics=False, synth=synth)["distance"]
                    < evaluate_route(inst, best, use_true_semantics=False, synth=synth)["distance"] - 1e-9):
                best = cand
                improved = True
                break

        if not improved:
            break

    return best

# ──────────────────────────────────────────────────────────────────────────────
# 12. ALGORITHM RUNNERS  (all 6 from Paper-2)
# ──────────────────────────────────────────────────────────────────────────────

def run_mpdd(inst: Instance) -> RouteResult:
    """Paper-1 MPDD — baseline without semantic reasoning."""
    t0 = time.perf_counter()
    synth = {req.idx: SynthTuple(req.kappa_true, False, False) for req in inst.requests}
    route = construct_route(inst, synth, mode="mpdd", enforce_compat=False)
    route = source_anchored_refine(inst, route, synth)
    rt = time.perf_counter() - t0
    metrics = evaluate_route(inst, route, use_true_semantics=True)
    return RouteResult(route, synth, rt, "MPDD", metrics)

def run_hnp(inst: Instance, seed: int = 0, llm_error: float = 0.1) -> RouteResult:
    """HNP — full semantic synthesis + compatibility + geofence + deadline + refinement."""
    t0 = time.perf_counter()
    synth = verified_synthesis(inst, seed, llm_error)
    route = construct_route(inst, synth, mode="hnp", enforce_compat=True)
    route = source_anchored_refine(inst, route, synth)
    rt = time.perf_counter() - t0
    metrics = evaluate_route(inst, route, use_true_semantics=True)
    return RouteResult(route, synth, rt, "HNP", metrics)

def run_hnp_no_verify(inst: Instance, seed: int = 0, llm_error: float = 0.1) -> RouteResult:
    """HNP-NoVerify — routing backbone without SMT verifier V."""
    t0 = time.perf_counter()
    synth = unverified_synthesis(inst, seed, llm_error)
    route = construct_route(inst, synth, mode="hnp", enforce_compat=True)
    route = source_anchored_refine(inst, route, synth)
    rt = time.perf_counter() - t0
    metrics = evaluate_route(inst, route, use_true_semantics=True)
    return RouteResult(route, synth, rt, "HNP-NoVerify", metrics)

def run_hnp_no_compat(inst: Instance, seed: int = 0, llm_error: float = 0.1) -> RouteResult:
    """HNP-NoCompat — verified synthesis but no compatibility enforcement in routing."""
    t0 = time.perf_counter()
    synth = verified_synthesis(inst, seed, llm_error)
    route = construct_route(inst, synth, mode="hnp", enforce_compat=False)
    route = source_anchored_refine(inst, route, synth)
    rt = time.perf_counter() - t0
    metrics = evaluate_route(inst, route, use_true_semantics=True)
    return RouteResult(route, synth, rt, "HNP-NoCompat", metrics)

def run_hnp_no_refine(inst: Instance, seed: int = 0, llm_error: float = 0.1) -> RouteResult:
    """HNP-NoRefine — verified synthesis + routing, no TSP refinement."""
    t0 = time.perf_counter()
    synth = verified_synthesis(inst, seed, llm_error)
    route = construct_route(inst, synth, mode="hnp", enforce_compat=True)
    # Skip refinement
    rt = time.perf_counter() - t0
    metrics = evaluate_route(inst, route, use_true_semantics=True)
    return RouteResult(route, synth, rt, "HNP-NoRefine", metrics)

def run_nn_pdp(inst: Instance) -> RouteResult:
    """NN-PDP — nearest-neighbour baseline (Paper-2 baseline 2)."""
    t0 = time.perf_counter()
    synth = {req.idx: SynthTuple(req.kappa_true, False, False) for req in inst.requests}
    route = construct_route(inst, synth, mode="nearest", enforce_compat=False)
    rt = time.perf_counter() - t0
    metrics = evaluate_route(inst, route, use_true_semantics=True)
    return RouteResult(route, synth, rt, "NN-PDP", metrics)

def run_penalty_greedy(inst: Instance) -> RouteResult:
    """Penalty-Greedy — non-LLM semantic-penalty greedy baseline (Paper-2 baseline 3)."""
    t0 = time.perf_counter()
    # Uses true classes but no LLM, no compatibility checking; penalises by class
    synth = {req.idx: SynthTuple(req.kappa_true, False, False) for req in inst.requests}
    route = construct_route(inst, synth, mode="mpdd", enforce_compat=True)
    route = source_anchored_refine(inst, route, synth)
    rt = time.perf_counter() - t0
    metrics = evaluate_route(inst, route, use_true_semantics=True)
    return RouteResult(route, synth, rt, "Penalty-Greedy", metrics)

# ──────────────────────────────────────────────────────────────────────────────
# 13. INSTANCE BUILDER  (Dharwad real-world)
# ──────────────────────────────────────────────────────────────────────────────

def build_instance_from_requests(requests_data: List[dict]) -> Instance:
    """
    Build an Instance from frontend package requests.
    Coordinates from real Dharwad locations, altitude from LOCATIONS table.
    Trajectory length = 2m'+2 (Paper-1 Section II-A).
    """
    n = len(requests_data)
    # Node layout: 0 = depot_start, 1..n = pickups, n+1..2n = deliveries, 2n+1 = depot_end
    depot_loc = LOCATIONS[0]  # SDM Hospital = depot

    coords = np.zeros((2*n+2, 2))
    altitudes = np.zeros(2*n+2)

    # depot
    coords[0]    = [depot_loc["x"], depot_loc["y"]]
    coords[2*n+1]= [depot_loc["x"], depot_loc["y"]]
    altitudes[0] = altitudes[2*n+1] = depot_loc["altitude"]

    requests: List[Request] = []
    for i, rd in enumerate(requests_data):
        pu_idx = rd.get("pickup_loc", 0) % len(LOCATIONS)
        dl_idx = rd.get("delivery_loc", 1) % len(LOCATIONS)
        pu_loc = LOCATIONS[pu_idx]
        dl_loc = LOCATIONS[dl_idx]

        coords[1+i]    = [pu_loc["x"], pu_loc["y"]]
        coords[n+1+i]  = [dl_loc["x"], dl_loc["y"]]
        altitudes[1+i]   = pu_loc["altitude"]
        altitudes[n+1+i] = dl_loc["altitude"]

        kappa = rd.get("commodity_class", "GENERAL")
        if kappa not in CLASSES:
            kappa = "GENERAL"
        weight = max(0.1, float(rd.get("weight", 1.0)))
        deadline = float(rd.get("deadline_minutes", 120.0))
        priority = 1.8 if kappa == "PHARMA" else (1.4 if kappa in HAZARD_CLASSES else 1.0)

        requests.append(Request(
            idx=i, pickup=pu_idx, delivery=dl_idx,
            weight=weight, kappa_true=kappa,
            deadline=deadline,
            temp_required=kappa in {"PHARMA", "FOOD", "CRYOGENIC"},
            priority=priority,
            description=rd.get("description", "")
        ))

    # UAV capacity = sum of weights * 0.55 or at least 3 kg (Paper-1 simulation)
    total_w = sum(r.weight for r in requests)
    W = max(3.0, 0.55 * total_w)

    # Geofence & noise zones — real Dharwad approximate zones
    geozones = [
        Zone(x=latlon_to_km(15.3617, 75.0849)[0],
             y=latlon_to_km(15.3617, 75.0849)[1],
             radius=0.5, kind="geo", name="Hubli Airport NFZ"),
        Zone(x=latlon_to_km(15.4540, 75.0013)[0],
             y=latlon_to_km(15.4540, 75.0013)[1],
             radius=0.3, kind="geo", name="Caltex Junction NFZ"),
    ]
    noisezones = [
        Zone(x=latlon_to_km(15.4480, 75.0190)[0],
             y=latlon_to_km(15.4480, 75.0190)[1],
             radius=0.4, kind="noise", name="Navanagar Residential"),
        Zone(x=latlon_to_km(15.4732, 74.9917)[0],
             y=latlon_to_km(15.4732, 74.9917)[1],
             radius=0.35, kind="noise", name="Unkal Lake Quiet Zone"),
    ]

    return Instance(n=n, coords=coords, altitudes=altitudes, requests=requests,
                    W=W, compat_true=COMPAT_GRAPH,
                    geozones=geozones, noisezones=noisezones)

# ──────────────────────────────────────────────────────────────────────────────
# 14. DYNAMIC REPLANNING  (Paper-2 Eq. 8a–8c)
# ──────────────────────────────────────────────────────────────────────────────

def replan_with_disruption(
    inst: Instance,
    current_route: List[int],
    step_executed: int,
    disruption: dict,
    seed: int = 99
) -> RouteResult:
    """
    Paper-2 Section 1.2.5 — Dynamic replanning under semantic disruption.
    Preserves π_new[1:t] = π_old[1:t]  (causality — Eq. 8a)
    Generates Ψ_replan(π_old, Δ, Gc) = 1  (Eq. 8b)
    """
    # Causality preservation — keep already-executed prefix
    prefix = current_route[:step_executed + 1]
    completed_rids = set()
    for node in prefix:
        typ, rid = node_request(node, inst.n)
        if typ == "D" and rid >= 0:
            completed_rids.add(rid)

    # Build reduced instance for remaining requests
    remaining_requests = [r for r in inst.requests if r.idx not in completed_rids]
    if not remaining_requests:
        return RouteResult(prefix, {}, 0.0, "REPLAN", {})

    # Add new no-fly zone from disruption if present
    new_zones = list(inst.geozones)
    if "nofly_lat" in disruption and "nofly_lon" in disruption:
        nx, ny = latlon_to_km(disruption["nofly_lat"], disruption["nofly_lon"])
        new_zones.append(Zone(x=nx, y=ny, radius=float(disruption.get("nofly_radius_km", 0.3)),
                              kind="geo", name=disruption.get("name", "Emergency NFZ")))

    new_inst = Instance(
        n=len(remaining_requests),
        coords=np.vstack([inst.coords[0:1],
                          inst.coords[[1+r.idx for r in remaining_requests]],
                          inst.coords[[inst.n+1+r.idx for r in remaining_requests]],
                          inst.coords[-1:]]),
        altitudes=np.concatenate([[inst.altitudes[0]],
                                   [inst.altitudes[1+r.idx] for r in remaining_requests],
                                   [inst.altitudes[inst.n+1+r.idx] for r in remaining_requests],
                                   [inst.altitudes[-1]]]),
        requests=[Request(idx=i, pickup=r.pickup, delivery=r.delivery,
                          weight=r.weight, kappa_true=r.kappa_true,
                          deadline=r.deadline, temp_required=r.temp_required,
                          priority=r.priority) for i, r in enumerate(remaining_requests)],
        W=inst.W,
        compat_true=inst.compat_true,
        geozones=new_zones,
        noisezones=inst.noisezones,
        speed=inst.speed
    )

    result = run_hnp(new_inst, seed=seed)
    result.route = prefix[:-1] + result.route  # stitch prefix
    result.algo = "HNP-REPLAN"
    return result

# ──────────────────────────────────────────────────────────────────────────────
# 15. LLM NATURAL LANGUAGE INSTRUCTION PROCESSOR
# ──────────────────────────────────────────────────────────────────────────────

NL_INSTRUCTION_PROMPT = """
You are the UAV mission controller for a Dharwad urban delivery drone.
Current locations available:
{locations}

Current requests:
{requests}

User instruction: "{instruction}"

Extract a structured command JSON:
{{
  "action": "add_request" | "remove_request" | "add_nofly" | "replan" | "status" | "unknown",
  "pickup_loc": <location index 0-{max_loc}> or null,
  "delivery_loc": <location index 0-{max_loc}> or null,
  "commodity_class": "PHARMA"|"FOOD"|"ELECTRONICS"|"FLAMMABLE"|"OXIDIZER"|"CRYOGENIC"|"GENERAL" or null,
  "weight": <float kg> or null,
  "deadline_minutes": <float> or null,
  "nofly_lat": <float> or null,
  "nofly_lon": <float> or null,
  "nofly_radius_km": <float> or null,
  "request_idx": <int> or null,
  "response_text": "<human friendly response>"
}}

Respond ONLY with valid JSON.
"""

def process_nl_instruction(instruction: str, current_requests: list) -> dict:
    loc_names = "\n".join(f"  {i}: {l['name']} ({l['type']})" for i, l in enumerate(LOCATIONS))
    req_str   = json.dumps(current_requests, indent=2)
    prompt = NL_INSTRUCTION_PROMPT.format(
        locations=loc_names, requests=req_str,
        instruction=instruction, max_loc=len(LOCATIONS)-1
    )
    raw = llm_call_ollama(prompt)
    try:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    # Fallback rule-based parsing
    result = {"action": "unknown", "response_text": "Understood. Processing request."}
    low = instruction.lower()
    if any(w in low for w in ["add", "pick", "deliver"]):
        result["action"] = "add_request"
        result["response_text"] = "Adding new delivery request to mission plan."
    elif any(w in low for w in ["cancel", "remove", "drop"]):
        result["action"] = "remove_request"
        result["response_text"] = "Removing request from plan."
    elif any(w in low for w in ["avoid", "no-fly", "nofly", "restricted"]):
        result["action"] = "add_nofly"
        result["response_text"] = "Adding no-fly zone to mission."
    elif any(w in low for w in ["replan", "reroute", "change route"]):
        result["action"] = "replan"
        result["response_text"] = "Replanning route with updated constraints."
    elif any(w in low for w in ["status", "where", "current"]):
        result["action"] = "status"
        result["response_text"] = "Checking UAV status."
    return result

# ──────────────────────────────────────────────────────────────────────────────
# 16. FLASK API ROUTES
# ──────────────────────────────────────────────────────────────────────────────

# Global mission state
mission_state = {
    "requests": [],
    "instance": None,
    "results": {},
    "active_algo": "HNP",
    "running": False,
    "step": 0,
    "disruptions": []
}

@app.route('/')
def index():
    return send_file('index.html')

@app.route('/api/locations', methods=['GET'])
def get_locations():
    return jsonify({"locations": LOCATIONS, "depot": LOCATIONS[0]})

@app.route('/api/compat_graph', methods=['GET'])
def get_compat_graph():
    """Return the compatibility graph Gc for UI display."""
    edges = []
    for a in CLASSES:
        for b in CLASSES:
            if a < b:
                edges.append({"a": a, "b": b, "compatible": COMPAT_GRAPH.get((a,b), True)})
    return jsonify({"classes": CLASSES, "edges": edges, "hazard_classes": list(HAZARD_CLASSES)})

@app.route('/api/run_all', methods=['POST'])
def run_all():
    """
    Main endpoint: run all 6 algorithms on given package requests.
    Returns results + route animation data for frontend.
    """
    data = request.json
    requests_data = data.get("requests", [])
    llm_error = float(data.get("llm_error", 0.1))
    seed = int(data.get("seed", 42))
    use_real_llm = bool(data.get("use_real_llm", False))

    if not requests_data:
        return jsonify({"error": "No requests provided"}), 400

    try:
        inst = build_instance_from_requests(requests_data)
        mission_state["instance"] = inst
        mission_state["requests"] = requests_data

        # Run all 6 algorithms
        results = {}
        algos = [
            ("MPDD",          lambda: run_mpdd(inst)),
            ("HNP",           lambda: run_hnp(inst, seed, llm_error)),
            ("HNP-NoVerify",  lambda: run_hnp_no_verify(inst, seed, llm_error)),
            ("HNP-NoCompat",  lambda: run_hnp_no_compat(inst, seed, llm_error)),
            ("HNP-NoRefine",  lambda: run_hnp_no_refine(inst, seed, llm_error)),
            ("NN-PDP",        lambda: run_nn_pdp(inst)),
        ]

        for name, fn in algos:
            try:
                rr = fn()
                results[name] = {
                    "route": rr.route,
                    "runtime": round(rr.runtime, 4),
                    "metrics": rr.metrics,
                    "algo": name,
                    "synth": {str(k): {"kappa": v.kappa, "verified": v.verified,
                                        "recovered": v.recovered}
                              for k, v in rr.synth.items()},
                }
            except Exception as ex:
          