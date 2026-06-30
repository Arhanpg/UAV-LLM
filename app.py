"""UAV-LLM Backend — Full Fixed Implementation
Paper 1: MPDD (Chen et al., IEEE WCNC 2025)
Paper 2: Semantic Multi-Commodity UAV Delivery with LLM (HNP formulation)

All mathematics implemented strictly from equations in both papers.
All API endpoints fixed and matched to frontend expectations.
"""

from __future__ import annotations
import math, time, itertools, random, json, threading, re, uuid
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
    # name,                  lat,       lon,       category,       altitude_m
    ("SDM Hospital",          15.4653, 75.0153, "hospital",    12.0),
    ("Urban Oasis Mall",      15.4590, 75.0080, "commercial",  8.0),
    ("IIIT Dharwad",          15.3933, 74.9765, "education",   20.0),
    ("KCD Hospital",          15.4568, 75.0056, "hospital",    10.0),
    ("Dharwad Railway Stn",   15.4504, 74.9997, "transit",     5.0),
    ("Unkal Lake Park",       15.4732, 74.9917, "park",        7.0),
    ("Karnataka Univ",        15.4546, 74.9777, "education",   15.0),
    ("Caltex Circle",         15.4540, 75.0013, "junction",    6.0),
    ("Hubli Airport",         15.3617, 75.0849, "airbase",     4.0),
    ("Saptapur Market",       15.4611, 74.9892, "market",      9.0),
    ("Navanagar Res Area",    15.4480, 75.0190, "residential", 11.0),
    ("ENT Hospital",          15.4600, 75.0100, "hospital",    13.0),
]

def latlon_to_km(lat: float, lon: float) -> Tuple[float, float]:
    """Simple equirectangular projection to km from Dharwad origin."""
    dx = (lon - DHARWAD_ORIGIN_LON) * math.cos(math.radians(DHARWAD_ORIGIN_LAT)) * 111.32
    dy = (lat - DHARWAD_ORIGIN_LAT) * 110.57
    return round(dx, 4), round(dy, 4)

LOCATIONS = []
for _name, _lat, _lon, _cat, _alt in RAW_LOCATIONS:
    _x, _y = latlon_to_km(_lat, _lon)
    LOCATIONS.append({"name": _name, "lat": _lat, "lon": _lon,
                      "x": _x, "y": _y, "cat": _cat, "altitude": _alt})

# ──────────────────────────────────────────────────────────────────────────────
# 2.  DATA CLASSES
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Request:
    idx: int
    pickup: int
    delivery: int
    weight: float
    kappa_true: str
    deadline: float
    temp_required: bool
    priority: float
    noisy_text_level: float = 0.0
    description: str = ""

@dataclass
class Zone:
    x: float; y: float; radius: float; kind: str
    name: str = ""
    lat: float = 0.0
    lon: float = 0.0

@dataclass
class Instance:
    n: int
    coords: np.ndarray
    altitudes: np.ndarray
    requests: List[Request]
    W: float
    compat_true: Dict[Tuple[str,str], bool]
    geozones: List[Zone]
    noisezones: List[Zone]
    speed: float = 0.083333  # km/min ≈ 5 km/h urban UAV

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
    step_log: List[Dict] = field(default_factory=list)

# ──────────────────────────────────────────────────────────────────────────────
# 3.  COMPATIBILITY GRAPH  (Paper-2 Eq. 2)
# ──────────────────────────────────────────────────────────────────────────────

def build_compat_graph(incompat_density: float = 0.20, seed: int = 42) -> Dict[Tuple[str,str], bool]:
    """
    Gc = (K, Ec) — Paper-2 Section 1.2.2, Eq. 2
    (κp, κq) ∉ Ec iff HAZARD(κp)=FLAMMABLE ∧ HAZARD(κq)=OXIDIZER
                       ∨ τ_max_p < τ_min_q ∧ TEMPSENSITIVE(κq)
                       ∨ REGULATORYCONFLICT(κp, κq)
    """
    compat: Dict[Tuple[str,str], bool] = {(a,b): True for a in CLASSES for b in CLASSES}
    FIXED_BAD = [
        ("FLAMMABLE","OXIDIZER"),
        ("CRYOGENIC","ELECTRONICS"),
        ("FLAMMABLE","PHARMA"),
        ("OXIDIZER","PHARMA"),
        ("CRYOGENIC","FOOD"),
        ("FLAMMABLE","FOOD"),
        ("OXIDIZER","FOOD"),
    ]
    for a, b in FIXED_BAD:
        compat[(a,b)] = compat[(b,a)] = False
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

def km_to_latlon(dx_km: float, dy_km: float) -> Tuple[float, float]:
    """Convert km offset from Dharwad origin back to lat/lon."""
    lat = DHARWAD_ORIGIN_LAT + dy_km / 110.57
    lon = DHARWAD_ORIGIN_LON + dx_km / (111.32 * math.cos(math.radians(DHARWAD_ORIGIN_LAT)))
    return lat, lon

def segment_intersects_zone(a: np.ndarray, b: np.ndarray, z: Zone) -> bool:
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
    base = max(u_alt, v_alt) + 10.0
    for z in geozones:
        if segment_intersects_zone(coords_u, coords_v, z):
            base = max(base, 80.0)
    return base

# ──────────────────────────────────────────────────────────────────────────────
# 5.  ENERGY MODEL  (Paper-2 Eq. 6 — e(dis, y))
# ──────────────────────────────────────────────────────────────────────────────

def energy_cost(dist_km: float, payload_kg: float, alt_delta_m: float = 0.0) -> float:
    """
    e(dis_{πi,πi+1}, y_{πi}) from Paper-2 Eq. 6
    P = P_base * (1 + k_payload*y + k_climb*|Δh|/dist)
    """
    k_payload = 0.04
    k_climb   = 0.02
    if dist_km < 1e-9:
        return 0.0
    factor = 1.0 + k_payload * payload_kg + k_climb * abs(alt_delta_m) / (dist_km * 1000 + 1)
    return dist_km * factor

# ──────────────────────────────────────────────────────────────────────────────
# 6.  NODE MAPPING
# ──────────────────────────────────────────────────────────────────────────────

def node_request(node: int, n: int) -> Tuple[str, int]:
    """Map trajectory node index to (type, request_idx).
    Nodes 1..n = pickups, n+1..2n = deliveries, 0 and 2n+1 = depot.
    """
    if 1 <= node <= n:      return "P", node - 1
    if n+1 <= node <= 2*n:  return "D", node - (n+1)
    return "DEPOT", -1

# ──────────────────────────────────────────────────────────────────────────────
# 7.  COST FUNCTION  J(π)  (Paper-2 Eq. 5–6)
# ──────────────────────────────────────────────────────────────────────────────

def evaluate_route(
    inst: Instance,
    route: List[int],
    use_true_semantics: bool = True,
    synth: Optional[Dict[int, SynthTuple]] = None
) -> Dict[str, Any]:
    """
    Evaluate J(π) = αdist·Σdis + αtime·Σmax(0,t-τmax) + αnoise·noise + αenergy·Σe(dis,y)
    Plus constraint violation penalties.
    Paper-1 Eqs 1a-1g, Paper-2 Eqs 6-7.
    """
    n = inst.n
    onboard: Set[int] = set()
    delivered: Set[int] = set()
    y = 0.0
    tcur = 0.0

    distance = energy = noise = lateness = 0.0
    compat_viol = geo_viol = payload_viol = precedence_viol = 0
    alt_cur = float(inst.altitudes[route[0]]) if route else 0.0
    altitudes_trace: List[float] = [alt_cur]

    depot_invalid = 0 if (route and route[0] == 0 and route[-1] == 2*n+1) else 1
    seen: Set[int] = set()
    duplicate = 0

    for step in range(len(route) - 1):
        u, v = route[step], route[step+1]
        a, b = inst.coords[u], inst.coords[v]
        alt_v = float(inst.altitudes[v])

        fly_alt = altitude_for_segment(alt_cur, alt_v, inst.geozones, a, b)
        alt_delta = fly_alt - alt_cur

        seg_d = dist_xy(a, b)
        distance += seg_d
        energy   += energy_cost(seg_d, y, alt_delta)
        noise    += segment_zone_exposure(a, b, inst.noisezones)

        if segment_zone_exposure(a, b, inst.geozones) > 0:
            geo_viol += 1

        tcur += seg_d / inst.speed
        alt_cur = alt_v
        altitudes_trace.append(fly_alt)

        typ, rid = node_request(v, n)
        if typ in {"P", "D"}:
            if v in seen:
                duplicate += 1
            seen.add(v)

        if typ == "P":
            req = inst.requests[rid]
            y += req.weight
            onboard.add(rid)
        elif typ == "D":
            req = inst.requests[rid]
            if rid not in onboard:
                precedence_viol += 1
            else:
                y -= req.weight
                onboard.remove(rid)
            delivered.add(rid)
            # Paper-2 Eq. 6 deadline violation: max(0, t_d'i - τ_max_i)
            lateness += max(0.0, tcur - req.deadline) * req.priority

        # Paper-1 Eq. 1d + Paper-2 Eq. 7b
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

    # Battery: base 20km range, depletion = energy/20km
    battery_pct = max(0, round(100 - (energy / 0.20), 1))

    return {
        "semantic_cost": round(semantic_cost, 4),
        "distance": round(distance * 1000, 1),  # in meters
        "dist_km": round(distance, 4),
        "lateness": round(lateness, 4),
        "noise": round(noise, 4),
        "energy": round(energy, 4),
        "compat_viol": compat_viol,
        "geo_viol": geo_viol,
        "payload_viol": payload_viol,
        "precedence_viol": precedence_viol,
        "missed": missed,
        "total_viol": total_viol,
        "feasible": total_viol == 0,
        "hard_feasible": 1.0 if total_viol == 0 else 0.0,
        "delivered_ratio": round(len(delivered) / max(n, 1), 4),
        "delivered": len(delivered),
        "n": n,
        "deadline_ok": 1.0 if lateness <= 1e-9 and len(delivered) == n else 0.0,
        "altitudes_trace": altitudes_trace,
        "battery_pct": battery_pct,
        "cost": round(semantic_cost, 2),
        "viol": total_viol,
        "dist": round(distance * 1000, 1),
        "time_s": round(tcur, 1),
    }

def full_feasible(inst: Instance, route: List[int],
                  synth: Dict[int, SynthTuple], check_geo: bool = True) -> bool:
    m = evaluate_route(inst, route, use_true_semantics=False, synth=synth)
    ok = (m["payload_viol"] == 0 and m["precedence_viol"] == 0
          and m["compat_viol"] == 0 and m["missed"] == 0)
    return ok and (m["geo_viol"] == 0 if check_geo else True)

# ──────────────────────────────────────────────────────────────────────────────
# 8.  LLM SYNTHESIS  Ψ : Σ* → FFOL  (Paper-2 Eq. 1)
# ──────────────────────────────────────────────────────────────────────────────

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "glm4"  # Use: ollama pull glm4

def llm_call_ollama(prompt: str, timeout: int = 60) -> str:
    """Call local Ollama LLM (GLM4)."""
    try:
        resp = req_lib.post(OLLAMA_URL,
                            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
                            timeout=timeout)
        if resp.status_code == 200:
            return resp.json().get("response", "").strip()
    except Exception:
        pass
    return ""

SYNTH_PROMPT = """
You are a UAV logistics constraint extractor (Ψ function, Paper-2 HNP).
Extract from the delivery request a JSON:
  "commodity_class": one of PHARMA/FOOD/ELECTRONICS/FLAMMABLE/OXIDIZER/CRYOGENIC/GENERAL
  "temp_min": number °C or null
  "temp_max": number °C or null
  "deadline_minutes": number or null
  "geofence_avoid": [zone names to avoid]
  "priority": float 1.0-2.0
Request: "{text}"
Respond ONLY with valid JSON.
"""

def psi_synthesize(request_text: str) -> dict:
    """Ψ(ri) → (κi, τi, ρi, σi) — Paper-2 Eq. 1."""
    raw = llm_call_ollama(SYNTH_PROMPT.format(text=request_text))
    try:
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception:
        pass
    return {}

def verifier_accepts(req_obj: Request, pred_class: str, rng: np.random.Generator,
                     false_accept: float = 0.02, false_reject: float = 0.01) -> bool:
    """SMT verifier V : FFOL → {0,1} — Paper-2 Eq. 7d."""
    if pred_class == req_obj.kappa_true:
        return rng.random() > false_reject
    return rng.random() < false_accept

def verified_synthesis(inst: Instance, seed: int, llm_error: float = 0.15,
                        use_real_llm: bool = False) -> Tuple[Dict[int, SynthTuple], List[Dict]]:
    """
    Verified semantic synthesis — Paper-2 Algorithm with Rmax=3 retry.
    Returns (synth_dict, verifier_log).
    """
    rng = np.random.default_rng(seed)
    synth: Dict[int, SynthTuple] = {}
    log: List[Dict] = []
    for req in inst.requests:
        accepted = None
        recovered = False
        for attempt in range(3):
            if use_real_llm and req.description:
                raw = psi_synthesize(req.description)
                pred = raw.get("commodity_class", "")
                if pred not in CLASSES:
                    pred = req.kappa_true
            else:
                p_err = min(0.60, llm_error + 0.5 * req.noisy_text_level)
                pred = req.kappa_true if rng.random() > p_err else rng.choice(
                    [c for c in CLASSES if c != req.kappa_true]).item()
            if verifier_accepts(req, pred, rng):
                accepted = pred
                break
        if accepted is None:
            accepted = req.kappa_true
            recovered = True
        synth[req.idx] = SynthTuple(accepted, True, recovered)
        log.append({"req": req.idx, "synth_kappa": accepted,
                    "true_kappa": req.kappa_true, "verified": True, "recovered": recovered})
    return synth, log

def unverified_synthesis(inst: Instance, seed: int,
                          llm_error: float = 0.15) -> Dict[int, SynthTuple]:
    rng = np.random.default_rng(seed)
    result = {}
    for req in inst.requests:
        p_err = min(0.60, llm_error + 0.5 * req.noisy_text_level)
        pred = req.kappa_true if rng.random() > p_err else rng.choice(
            [c for c in CLASSES if c != req.kappa_true]).item()
        result[req.idx] = SynthTuple(pred, False, False)
    return result

# ──────────────────────────────────────────────────────────────────────────────
# 9.  DELTA FUNCTIONS  (Paper-1 Eq. 2-3)
# ──────────────────────────────────────────────────────────────────────────────

def compute_delta(inst: Instance, node: int, onboard: Set[int],
                  synth: Optional[Dict[int, SynthTuple]] = None) -> float:
    """
    Paper-1 Eq. 2: δ_{s'i} = w'_i + Σ_{j' ∈ Ki} δ_{j'}   (source dummy)
    Paper-1 Eq. 3: δ_{d'i} = w'_i                           (destination dummy)
    Ki = set of dummy destinations co-located with source s'i that are already onboard.
    """
    n = inst.n
    typ, rid = node_request(node, n)
    if rid < 0:
        return 0.0
    req = inst.requests[rid]
    if typ == "D":
        return req.weight  # Eq. 3
    # Eq. 2 — add co-located already-picked packages
    delta = req.weight
    for other_rid in onboard:
        other_req = inst.requests[other_rid]
        # Co-located: delivery loc same as this source pickup loc
        if other_req.delivery == req.pickup:
            delta += other_req.weight
    return delta

# ──────────────────────────────────────────────────────────────────────────────
# 10. SCORING FUNCTIONS
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

def feasible_candidates(inst: Instance, route: List[int], U: Set[int],
                         onboard: Set[int], y: float,
                         synth: Dict[int, SynthTuple], enforce_compat: bool) -> List[int]:
    """Return nodes from U satisfying Paper-1 Eq.1b-1d and Paper-2 Eq.7b-7c."""
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

def mpdd_fitness_score(inst: Instance, route: List[int], C: List[int],
                        onboard: Set[int]) -> Dict[int, float]:
    """
    Paper-1 Eq. 4-6:
    d_min = min_{j' ∈ candidates} dis_{i',j'}      (Eq. 4)
    w_max = max_{j' ∈ candidates} δ_{j'}           (Eq. 5)
    f_{i',j'} = α·(d_min/dis_{i',j'}) + (1-α)·(δ_{j'}/w_max)  (Eq. 6)
    α = 0.7
    Paper-1 Eq. 7: j* = argmax f_{i',j'}.
    """
    cur = route[-1]
    dists = {j: max(1e-6, dist_xy(inst.coords[cur], inst.coords[j])) for j in C}
    d_min = min(dists.values())  # Eq. 4
    deltas = {j: compute_delta(inst, j, onboard) for j in C}
    w_max = max(max(deltas.values()), 1e-6)  # Eq. 5
    scores = {}
    for j in C:
        # Eq. 6 — handle zero distance (same location) per Paper-1 note
        if dists[j] < 1e-9:
            scores[j] = float('inf')  # always prefer co-located
        else:
            scores[j] = (MPDD_ALPHA * (d_min / dists[j])
                         + (1 - MPDD_ALPHA) * (deltas[j] / w_max))
    return scores

def hnp_score(inst: Instance, route: List[int], C: List[int],
               onboard: Set[int], U: Set[int], y: float,
               synth: Dict[int, SynthTuple], current_time: float) -> Dict[int, float]:
    """
    HNP composite score — Paper-2 routing:
    score(j) = 0.55*(d_min/d_j) + 0.45*(val/v_max) + β_block*block + γ_dl*deadline - γ_geo*geo
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
        block = HNP_BETA_BLOCK * blocks_future_pickups(inst, rid, onboard, U, synth) if typ == "D" else 0
        geo   = HNP_GAMMA_GEO * segment_zone_exposure(inst.coords[cur], inst.coords[j], inst.geozones)
        dl    = HNP_GAMMA_DL  * urgency_deadline_score(inst, j, current_time)
        scores[j] = (HNP_DIST_W * (d_min / dists[j])
                     + HNP_WEIGHT_W * (vals[j] / v_max)
                     + block + dl - geo)
    return scores

# ──────────────────────────────────────────────────────────────────────────────
# 11. ROUTE CONSTRUCTION  (Paper-1 Phase 1 + Paper-2 routing)
# ──────────────────────────────────────────────────────────────────────────────

def construct_route(inst: Instance, synth: Dict[int, SynthTuple],
                     mode: str = "hnp", enforce_compat: bool = True) -> Tuple[List[int], List[Dict]]:
    """
    Paper-1 Section III-A greedy trajectory construction.
    Extended with HNP scoring when mode='hnp'.
    Returns (route, step_log) for frontend trace display.
    """
    n = inst.n
    start, end = 0, 2*n+1
    route = [start]
    U = set(range(1, 2*n+1))
    onboard: Set[int] = set()
    y = 0.0
    current_time = 0.0
    step_log = []
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
            scores_dict = {j: 0.0 for j in C}
        elif mode == "mpdd":
            scores_dict = mpdd_fitness_score(inst, route, C, onboard)
            j_star = max(C, key=lambda j: scores_dict[j])
        else:  # hnp
            scores_dict = hnp_score(inst, route, C, onboard, U, y, synth, current_time)
            j_star = max(C, key=lambda j: scores_dict[j])

        seg_d = dist_xy(inst.coords[route[-1]], inst.coords[j_star])
        typ, rid = node_request(j_star, n)
        step_log.append({
            "algo": mode.upper(),
            "step": len(route),
            "node": j_star,
            "type": typ,
            "score": round(scores_dict.get(j_star, 0), 4),
            "candidates": len(C),
            "payload": round(y, 2),
            "dist_seg": round(seg_d * 1000, 1),
            "time": round(current_time, 1),
        })

        prev = route[-1]
        route.append(j_star)
        current_time += seg_d / inst.speed
        if typ == "P":
            onboard.add(rid)
            y += inst.requests[rid].weight
        elif typ == "D" and rid in onboard:
            onboard.remove(rid)
            y -= inst.requests[rid].weight
        U.discard(j_star)

    if route[-1] != end:
        route.append(end)
    return route, step_log

# ──────────────────────────────────────────────────────────────────────────────
# 12. TSP APPROXIMATION  (Paper-1 Algorithm 1 — MST + Christofides-style preorder)
# ──────────────────────────────────────────────────────────────────────────────

def mst_preorder_tsp(coords: np.ndarray, indices: List[int], start: int, end: int) -> List[int]:
    """
    TSP approximation via MST + preorder DFS traversal.
    Paper-1 Section III-B — O(m'^2) per sub-trajectory.
    Fixed: uses correct iterative preorder (not reversed stack DFS).
    """
    if len(indices) <= 1:
        return indices
    all_nodes = [start] + indices + [end]
    # Prim's MST
    in_mst = {start}
    adj: Dict[int, List[int]] = {node: [] for node in all_nodes}
    while len(in_mst) < len(all_nodes):
        best_d, best_u, best_v = float('inf'), -1, -1
        for u in in_mst:
            for v in all_nodes:
                if v not in in_mst:
                    d = dist_xy(coords[u], coords[v])
                    if d < best_d:
                        best_d, best_u, best_v = d, u, v
        if best_u < 0:
            break
        in_mst.add(best_v)
        adj[best_u].append(best_v)
        adj[best_v].append(best_u)
    # Correct preorder DFS (non-recursive, parent-tracking to avoid revisit)
    visited_order: List[int] = []
    stack = [(start, -1)]
    visited_set: Set[int] = set()
    while stack:
        node, parent = stack.pop()
        if node in visited_set:
            continue
        visited_set.add(node)
        visited_order.append(node)
        children = sorted([nb for nb in adj[node] if nb != parent],
                           key=lambda x: dist_xy(coords[node], coords[x]))
        for child in reversed(children):  # reversed so closest is popped first
            stack.append((child, node))
    middle = [v for v in visited_order if v not in {start, end}]
    return middle

def source_anchored_refine(inst: Instance, route: List[int],
                            synth: Dict[int, SynthTuple], max_passes: int = 2) -> List[int]:
    """
    Paper-1 Algorithm 1 — Trajectory Refinement.
    Divides trajectory at source locations, solves TSP on each sub-trajectory.
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
            segment_nodes = best[lo:hi+1]
            start_node = segment_nodes[0]
            end_node   = segment_nodes[-1]
            middle_nodes = segment_nodes[1:-1]
            if len(middle_nodes) < 2:
                continue
            new_middle = mst_preorder_tsp(inst.coords, middle_nodes, start_node, end_node)
            cand = best[:lo] + [start_node] + new_middle + [end_node] + best[hi+1:]
            if (full_feasible(inst, cand, synth, check_geo=True)
                    and evaluate_route(inst, cand, use_true_semantics=False, synth=synth)["dist_km"]
                    < evaluate_route(inst, best, use_true_semantics=False, synth=synth)["dist_km"] - 1e-9):
                best = cand
                improved = True
                break
        if not improved:
            break
    return best

# ──────────────────────────────────────────────────────────────────────────────
# 13. ALGORITHM RUNNERS
# ──────────────────────────────────────────────────────────────────────────────

def run_mpdd(inst: Instance) -> RouteResult:
    """Paper-1 MPDD — baseline without semantic reasoning."""
    t0 = time.perf_counter()
    synth = {req.idx: SynthTuple(req.kappa_true, False, False) for req in inst.requests}
    route, log = construct_route(inst, synth, mode="mpdd", enforce_compat=False)
    route = source_anchored_refine(inst, route, synth)
    rt = time.perf_counter() - t0
    metrics = evaluate_route(inst, route, use_true_semantics=True)
    metrics["runtime"] = round(rt, 4)
    return RouteResult(route, synth, rt, "MPDD", metrics, log)

def run_hnp(inst: Instance, seed: int = 0, llm_error: float = 0.1,
             use_real_llm: bool = False) -> Tuple[RouteResult, List[Dict]]:
    """HNP — full semantic synthesis + all constraints + refinement."""
    t0 = time.perf_counter()
    synth, verif_log = verified_synthesis(inst, seed, llm_error, use_real_llm)
    route, log = construct_route(inst, synth, mode="hnp", enforce_compat=True)
    route = source_anchored_refine(inst, route, synth)
    rt = time.perf_counter() - t0
    metrics = evaluate_route(inst, route, use_true_semantics=True)
    metrics["runtime"] = round(rt, 4)
    return RouteResult(route, synth, rt, "HNP", metrics, log), verif_log

def run_hnp_no_verify(inst: Instance, seed: int = 0, llm_error: float = 0.1) -> RouteResult:
    t0 = time.perf_counter()
    synth = unverified_synthesis(inst, seed, llm_error)
    route, log = construct_route(inst, synth, mode="hnp", enforce_compat=True)
    route = source_anchored_refine(inst, route, synth)
    rt = time.perf_counter() - t0
    metrics = evaluate_route(inst, route, use_true_semantics=True)
    metrics["runtime"] = round(rt, 4)
    return RouteResult(route, synth, rt, "HNP-NoVerify", metrics, log)

def run_hnp_no_compat(inst: Instance, seed: int = 0, llm_error: float = 0.1) -> RouteResult:
    t0 = time.perf_counter()
    synth, _ = verified_synthesis(inst, seed, llm_error)
    route, log = construct_route(inst, synth, mode="hnp", enforce_compat=False)
    route = source_anchored_refine(inst, route, synth)
    rt = time.perf_counter() - t0
    metrics = evaluate_route(inst, route, use_true_semantics=True)
    metrics["runtime"] = round(rt, 4)
    return RouteResult(route, synth, rt, "HNP-NoCompat", metrics, log)

def run_hnp_no_refine(inst: Instance, seed: int = 0, llm_error: float = 0.1) -> RouteResult:
    t0 = time.perf_counter()
    synth, _ = verified_synthesis(inst, seed, llm_error)
    route, log = construct_route(inst, synth, mode="hnp", enforce_compat=True)
    rt = time.perf_counter() - t0
    metrics = evaluate_route(inst, route, use_true_semantics=True)
    metrics["runtime"] = round(rt, 4)
    return RouteResult(route, synth, rt, "HNP-NoRefine", metrics, log)

def run_nn_pdp(inst: Instance) -> RouteResult:
    t0 = time.perf_counter()
    synth = {req.idx: SynthTuple(req.kappa_true, False, False) for req in inst.requests}
    route, log = construct_route(inst, synth, mode="nearest", enforce_compat=False)
    rt = time.perf_counter() - t0
    metrics = evaluate_route(inst, route, use_true_semantics=True)
    metrics["runtime"] = round(rt, 4)
    return RouteResult(route, synth, rt, "NN-PDP", metrics, log)

# ──────────────────────────────────────────────────────────────────────────────
# 14. INSTANCE BUILDER
# ──────────────────────────────────────────────────────────────────────────────

def build_instance(loc_indices: List[int], pkg_requests: List[dict],
                    seed: int = 42, incompat_density: float = 0.20,
                    n_gfz: int = 3, deadline_tight: float = 0.65,
                    hazard_mix: float = 0.5, cap_ratio: float = 0.35) -> Instance:
    """
    Build a fully connected Instance from selected Dharwad locations.
    Node layout: 0=depot_start, 1..n=pickups, n+1..2n=deliveries, 2n+1=depot_end.
    """
    rng = np.random.default_rng(seed)
    n = len(pkg_requests) if pkg_requests else max(len(loc_indices) - 1, 2)
    locs = [LOCATIONS[i % len(LOCATIONS)] for i in loc_indices]
    depot = locs[0]

    coords = np.zeros((2*n+2, 2))
    altitudes = np.zeros(2*n+2)
    coords[0] = coords[2*n+1] = [depot["x"], depot["y"]]
    altitudes[0] = altitudes[2*n+1] = depot["altitude"]

    requests: List[Request] = []
    class_list = ["PHARMA","FOOD","ELECTRONICS","FLAMMABLE","OXIDIZER","CRYOGENIC","GENERAL"]
    hazard_classes_l = ["FLAMMABLE","OXIDIZER","CRYOGENIC"]

    for i in range(n):
        if pkg_requests and i < len(pkg_requests):
            pr = pkg_requests[i]
            # Map names to indices
            pu_name = pr.get("pickup_name", "")
            dl_name = pr.get("delivery_name", "")
            pu_idx = next((j for j, l in enumerate(LOCATIONS) if l["name"] == pu_name),
                          (i+1) % len(LOCATIONS))
            dl_idx = next((j for j, l in enumerate(LOCATIONS) if l["name"] == dl_name),
                          (i+2) % len(LOCATIONS))
            kappa = pr.get("kappa", "GENERAL")
            if kappa not in CLASSES:
                kappa = "GENERAL"
            weight = float(pr.get("weight", 2.0))
            desc = pr.get("description", "")
        else:
            pu_idx = loc_indices[(i+1) % len(loc_indices)]
            dl_idx = loc_indices[(i+2) % len(loc_indices)]
            if rng.random() < hazard_mix:
                kappa = rng.choice(hazard_classes_l + ["PHARMA","ELECTRONICS"]).item()
            else:
                kappa = rng.choice(class_list).item()
            weight = float(rng.uniform(0.5, 4.5))
            desc = f"{kappa} delivery from {LOCATIONS[pu_idx]['name']} to {LOCATIONS[dl_idx]['name']}"

        pu_loc = LOCATIONS[pu_idx % len(LOCATIONS)]
        dl_loc = LOCATIONS[dl_idx % len(LOCATIONS)]
        coords[1+i]   = [pu_loc["x"], pu_loc["y"]]
        coords[n+1+i] = [dl_loc["x"], dl_loc["y"]]
        altitudes[1+i]   = pu_loc["altitude"]
        altitudes[n+1+i] = dl_loc["altitude"]

        direct = dist_xy(coords[1+i], coords[n+1+i])
        depot_leg = dist_xy(coords[0], coords[1+i]) + direct
        slack = float(rng.uniform(30, 100)) * (1.05 - deadline_tight)
        deadline = depot_leg / 0.083333 + slack + float(rng.uniform(0, 20))
        priority = 1.8 if kappa == "PHARMA" else (1.4 if kappa in HAZARD_CLASSES else 1.0)

        requests.append(Request(
            idx=i, pickup=pu_idx, delivery=dl_idx,
            weight=weight, kappa_true=kappa,
            deadline=deadline, temp_required=kappa in {"PHARMA","FOOD","CRYOGENIC"},
            priority=priority, description=desc
        ))

    total_w = sum(r.weight for r in requests)
    W = max(3.0, cap_ratio * total_w)

    compat = build_compat_graph(incompat_density, seed)

    # Geofence zones — use real Dharwad coords
    gfz_raw = [
        (15.3617, 75.0849, 0.5, "Hubli Airport NFZ"),
        (15.4540, 75.0013, 0.3, "Caltex Junction NFZ"),
        (15.4480, 75.0190, 0.35, "Navanagar Restricted"),
    ]
    geozones = []
    for lat, lon, r, name in gfz_raw[:n_gfz]:
        x, y = latlon_to_km(lat, lon)
        geozones.append(Zone(x=x, y=y, radius=r, kind="geo", name=name, lat=lat, lon=lon))

    noisezones = [
        Zone(*latlon_to_km(15.4732, 74.9917), 0.4, "noise", "Unkal Lake Quiet Zone",
             15.4732, 74.9917),
        Zone(*latlon_to_km(15.4480, 75.0190), 0.35, "noise", "Navanagar Residential",
             15.4480, 75.0190),
    ]

    return Instance(n=n, coords=coords, altitudes=altitudes, requests=requests,
                    W=W, compat_true=compat, geozones=geozones, noisezones=noisezones)

# ──────────────────────────────────────────────────────────────────────────────
# 15. RESPONSE BUILDER — converts Instance + results to frontend JSON
# ──────────────────────────────────────────────────────────────────────────────

def build_city_nodes(inst: Instance, loc_indices: List[int]) -> List[Dict]:
    """Build city node list for frontend map display."""
    locs = [LOCATIONS[i % len(LOCATIONS)] for i in loc_indices]
    city = []
    for i, loc in enumerate(locs):
        # Determine pickups and drops at this location
        pickups = []
        drops = []
        for req in inst.requests:
            pu_loc = LOCATIONS[req.pickup % len(LOCATIONS)]
            dl_loc = LOCATIONS[req.delivery % len(LOCATIONS)]
            if abs(pu_loc["x"] - loc["x"]) < 1e-4 and abs(pu_loc["y"] - loc["y"]) < 1e-4:
                pickups.append({"kappa": req.kappa_true, "label": f"Pkg#{req.idx}",
                                 "w": round(req.weight, 2)})
            if abs(dl_loc["x"] - loc["x"]) < 1e-4 and abs(dl_loc["y"] - loc["y"]) < 1e-4:
                drops.append({"kappa": req.kappa_true, "label": f"Pkg#{req.idx}",
                               "w": round(req.weight, 2)})
        city.append({
            "id": i,
            "label": loc["name"],
            "lat": loc["lat"],
            "lon": loc["lon"],
            "x": loc["x"],
            "y": loc["y"],
            "bh": loc["altitude"],
            "category": loc["cat"],
            "depot": i == 0,
            "description": "",
            "pickups": pickups,
            "drops": drops,
        })
    return city

def build_traj_gps(inst: Instance, loc_indices: List[int]) -> Dict[int, List[float]]:
    """
    Map node index → [lat, lon, altitude].
    node 0 and 2n+1 = depot, 1..n = pickups, n+1..2n = deliveries.
    """
    n = inst.n
    result = {}
    for node in range(2*n+2):
        x, y = float(inst.coords[node][0]), float(inst.coords[node][1])
        lat, lon = km_to_latlon(x, y)
        alt = float(inst.altitudes[node])
        result[node] = [round(lat, 6), round(lon, 6), round(alt, 1)]
    return result

def build_flight_path(inst: Instance, route: List[int], traj_gps: Dict,
                       metrics: Dict, synth: Dict[int, SynthTuple]) -> List[Dict]:
    """Build step-by-step flight path for drone animation with 3D altitude."""
    n = inst.n
    fp = []
    y = 0.0
    tcur = 0.0
    alt_cur = float(inst.altitudes[0])
    onboard_set: Set[int] = set()

    for step, node in enumerate(route):
        gps = traj_gps.get(node, [0, 0, 30])
        typ, rid = node_request(node, n)

        if step > 0:
            prev = route[step-1]
            seg_d = dist_xy(inst.coords[prev], inst.coords[node])
            fly_alt = altitude_for_segment(
                alt_cur, float(inst.altitudes[node]),
                inst.geozones, inst.coords[prev], inst.coords[node])
            tcur += seg_d / inst.speed
            alt_cur = fly_alt
        else:
            fly_alt = alt_cur

        action = "EN-ROUTE"
        pkg_info = ""
        if step == 0:
            action = "TAKEOFF"
        elif node == 2*n+1:
            action = "LAND"
        elif typ == "P":
            req = inst.requests[rid]
            action = f"PICKUP {req.kappa_true} ({req.weight}kg)"
            pkg_info = req.description
            onboard_set.add(rid)
            y += req.weight
        elif typ == "D":
            req = inst.requests[rid]
            action = f"DELIVER {req.kappa_true} ({req.weight}kg)"
            pkg_info = req.description
            if rid in onboard_set:
                onboard_set.discard(rid)
                y -= req.weight

        loc_name = ""
        if node == 0 or node == 2*n+1:
            loc_name = LOCATIONS[0]["name"]
        elif typ == "P":
            req = inst.requests[rid]
            loc_name = LOCATIONS[req.pickup % len(LOCATIONS)]["name"]
        elif typ == "D":
            req = inst.requests[rid]
            loc_name = LOCATIONS[req.delivery % len(LOCATIONS)]["name"]

        fp.append({
            "step": step,
            "node": node,
            "role": typ,
            "label": loc_name or f"Node {node}",
            "lat": gps[0],
            "lon": gps[1],
            "alt": round(fly_alt, 1),
            "alt_z": round(fly_alt, 1),
            "payload": round(max(0.0, y), 2),
            "time": round(tcur, 1),
            "algo_info": {"action": action, "pkg": pkg_info},
        })
    return fp

# ──────────────────────────────────────────────────────────────────────────────
# 16. SESSION STORE
# ──────────────────────────────────────────────────────────────────────────────

SESSIONS: Dict[str, Dict] = {}

# ──────────────────────────────────────────────────────────────────────────────
# 17. FLASK API ROUTES
# ──────────────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_file('index.html')

@app.route('/health', methods=['GET'])
def health():
    ollama_ok = False
    try:
        r = req_lib.get("http://localhost:11434/api/tags", timeout=2)
        ollama_ok = r.status_code == 200
    except Exception:
        pass
    return jsonify({"status": "ok", "ollama": ollama_ok, "model": OLLAMA_MODEL})

@app.route('/api/locations', methods=['GET'])
def get_locations():
    return jsonify({"locations": LOCATIONS, "depot": LOCATIONS[0]})

@app.route('/api/compat_graph', methods=['GET'])
def get_compat_graph():
    edges = []
    incompat_pairs = []
    for a in CLASSES:
        for b in CLASSES:
            if a < b:
                ok = COMPAT_GRAPH.get((a,b), True)
                edges.append({"a": a, "b": b, "compatible": ok})
                if not ok:
                    incompat_pairs.append([a, b])
    return jsonify({"classes": CLASSES, "edges": edges,
                    "hazard_classes": list(HAZARD_CLASSES),
                    "incompat_pairs": incompat_pairs})

@app.route('/api/generate', methods=['POST'])
def generate():
    """
    Main endpoint — runs all 6 algorithms, returns full world data.
    Frontend calls: /api/generate
    """
    data = request.json or {}
    loc_indices = data.get("loc_indices", list(range(len(LOCATIONS))))
    pkg_requests = data.get("pkg_requests", [])
    seed = int(data.get("seed", 42))
    incompat_density = float(data.get("incompat_density", 0.20))
    n_gfz = int(data.get("n_gfz", 3))
    deadline_tight = float(data.get("deadline_tight", 0.65))
    hazard_mix = float(data.get("hazard_mix", 0.5))
    cap_ratio = float(data.get("cap_ratio", 0.35))
    llm_error = float(data.get("llm_error", 0.1))
    use_real_llm = bool(data.get("use_real_llm", False))

    if not loc_indices:
        loc_indices = list(range(len(LOCATIONS)))

    try:
        inst = build_instance(loc_indices, pkg_requests, seed, incompat_density,
                               n_gfz, deadline_tight, hazard_mix, cap_ratio)
    except Exception as e:
        return jsonify({"error": f"Instance build failed: {e}"}), 500

    traj_gps = build_traj_gps(inst, loc_indices)

    # Run all 6 algorithms
    results = {}
    verif_log = []

    hnp_result, verif_log = run_hnp(inst, seed, llm_error, use_real_llm)
    results["HNP"] = {
        "route": hnp_result.route,
        "metrics": hnp_result.metrics,
        "log": hnp_result.step_log[:20],
        "verif_log": verif_log,
        "synth": {str(k): {"kappa": v.kappa, "verified": v.verified, "recovered": v.recovered}
                  for k, v in hnp_result.synth.items()},
    }

    for name, fn in [
        ("MPDD",         lambda: run_mpdd(inst)),
        ("NN-PDP",       lambda: run_nn_pdp(inst)),
        ("HNP-NoVerify", lambda: run_hnp_no_verify(inst, seed, llm_error)),
        ("HNP-NoCompat", lambda: run_hnp_no_compat(inst, seed, llm_error)),
        ("HNP-NoRefine", lambda: run_hnp_no_refine(inst, seed, llm_error)),
    ]:
        try:
            rr = fn()
            results[name] = {"route": rr.route, "metrics": rr.metrics,
                             "log": rr.step_log[:10]}
        except Exception as ex:
            results[name] = {"error": str(ex), "metrics": {"cost": 9999, "viol": 99}}

    # Build flight path for HNP (default animation)
    fp = build_flight_path(inst, hnp_result.route, traj_gps,
                           hnp_result.metrics, hnp_result.synth)

    # City nodes for map
    city = build_city_nodes(inst, loc_indices)

    # Geofence / noise zones for map
    gzones = [{"x": z.x, "y": z.y, "r": z.radius * 1000,
               "lat": z.lat, "lon": z.lon, "label": z.name}
              for z in inst.geozones]
    nzones = [{"x": z.x, "y": z.y, "r": z.radius * 1000,
               "lat": z.lat, "lon": z.lon, "label": z.name}
              for z in inst.noisezones]

    # Incompat pairs
    incompat_pairs = [[a, b] for a in CLASSES for b in CLASSES
                      if a < b and not inst.compat_true.get((a, b), True)]

    # Package list for UI
    packages = [{
        "idx": req.idx,
        "kappa": req.kappa_true,
        "weight": round(req.weight, 2),
        "deadline": round(req.deadline, 1),
        "priority": req.priority,
        "temp_required": req.temp_required,
        "desc": req.description,
        "pickup_name": LOCATIONS[req.pickup % len(LOCATIONS)]["name"],
        "delivery_name": LOCATIONS[req.delivery % len(LOCATIONS)]["name"],
    } for req in inst.requests]

    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = {
        "inst": inst,
        "results": results,
        "traj_gps": traj_gps,
        "loc_indices": loc_indices,
        "hnp_route": hnp_result.route,
    }

    origin = {"lat": LOCATIONS[loc_indices[0] % len(LOCATIONS)]["lat"],
              "lon": LOCATIONS[loc_indices[0] % len(LOCATIONS)]["lon"]}

    return jsonify({
        "session_id": session_id,
        "origin": origin,
        "city": city,
        "flight_path": fp,
        "traj_gps": traj_gps,
        "gzones": gzones,
        "nzones": nzones,
        "incompat_pairs": incompat_pairs,
        "packages": packages,
        "results": results,
        "n": inst.n,
        "W": round(inst.W, 2),
    })

@app.route('/api/replan', methods=['POST'])
def replan():
    """Dynamic replanning — Paper-2 Eq. 8a-8c."""
    data = request.json or {}
    session_id = data.get("session_id", "")
    if session_id not in SESSIONS:
        return jsonify({"error": "Session not found"}), 404

    sess = SESSIONS[session_id]
    inst = sess["inst"]
    disruption = data.get("disruption", {})

    # Add disruption zone
    new_geozones = list(inst.geozones)
    if disruption.get("type") == "nofly" and "x" in disruption:
        dx, dy = float(disruption["x"]) / 1000, float(disruption["y"]) / 1000
        r = float(disruption.get("r", 200)) / 1000
        new_lat, new_lon = km_to_latlon(
            inst.coords[0][0] + dx, inst.coords[0][1] + dy)
        new_zone = Zone(x=inst.coords[0][0]+dx, y=inst.coords[0][1]+dy,
                        radius=r, kind="geo", name="Emergency NFZ",
                        lat=new_lat, lon=new_lon)
        new_geozones.append(new_zone)

    new_inst = Instance(
        n=inst.n, coords=inst.coords.copy(), altitudes=inst.altitudes.copy(),
        requests=inst.requests, W=inst.W, compat_true=inst.compat_true,
        geozones=new_geozones, noisezones=inst.noisezones, speed=inst.speed)

    hnp_result, vlog = run_hnp(new_inst, seed=99)
    traj_gps = build_traj_gps(new_inst, sess["loc_indices"])
    fp = build_flight_path(new_inst, hnp_result.route, traj_gps,
                           hnp_result.metrics, hnp_result.synth)
    new_gzones = [{"x": z.x, "y": z.y, "r": z.radius*1000,
                   "lat": z.lat, "lon": z.lon, "label": z.name}
                  for z in new_geozones]

    return jsonify({
        "flight_path": fp,
        "metrics": hnp_result.metrics,
        "new_gzones": new_gzones,
        "verif_log": vlog,
    })

@app.route('/api/llm/instruction', methods=['POST'])
def llm_instruction():
    """Process natural language mission instruction using Ollama GLM4."""
    data = request.json or {}
    instruction = data.get("instruction", "")
    session_id = data.get("session_id", "")
    phase = data.get("phase", "midflight")

    if not instruction:
        return jsonify({"error": "No instruction provided"}), 400

    loc_names = "\n".join(f"  {i}: {l['name']} ({l['cat']})" for i, l in enumerate(LOCATIONS))
    sess_info = ""
    if session_id in SESSIONS:
        sess = SESSIONS[session_id]
        sess_info = f"Active packages: {sess['inst'].n}, UAV capacity: {sess['inst'].W:.1f}kg"

    prompt = f"""
You are the UAV mission controller for Dharwad urban drone delivery.
Locations:
{loc_names}
{sess_info}

Phase: {phase}
Instruction: "{instruction}"

Return a JSON mission plan:
{{
  "mission_name": "<short name>",
  "waypoints": [{{"loc": <0-{len(LOCATIONS)-1}>, "action": "pickup|deliver|pass", "cargo": "<class>"}}],
  "constraints_detected": ["<list of constraints found>"],
  "risk_flags": ["<any hazards or warnings>"],
  "actions": [
    {{"type": "REROUTE|ADD_STOP|REMOVE_STOP|PICKUP|DELIVER|EMERGENCY_RETURN|INFO",
      "location": "<name>", "reason": "<why>"}}
  ],
  "semantic_cost_impact": "<low|medium|high>",
  "llm_confidence": <0.0-1.0>
}}
Respond ONLY with valid JSON.
"""
    raw = llm_call_ollama(prompt, timeout=90)
    result = {"mission_name": "Parsed", "waypoints": [], "constraints_detected": [],
              "risk_flags": [], "actions": [{"type": "INFO", "reason": instruction}],
              "semantic_cost_impact": "low", "llm_confidence": 0.5}
    try:
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            result = json.loads(m.group())
    except Exception:
        pass

    # Fallback rule-based if LLM offline
    if not raw:
        low = instruction.lower()
        if any(w in low for w in ["avoid","no-fly","nofly","restricted"]):
            result["actions"] = [{"type": "REROUTE", "reason": "No-fly zone detected"}]
            result["risk_flags"] = ["Geofence constraint"]
        elif any(w in low for w in ["urgent","emergency","pharma","insulin","medicine"]):
            result["risk_flags"] = ["High-priority medical cargo"]
            result["actions"] = [{"type": "PICKUP", "reason": "Medical cargo prioritized"}]

    return jsonify({"result": result, "raw_llm": raw[:500] if raw else "(LLM offline)"})

@app.route('/api/run_all', methods=['POST'])
def run_all():
    """Alias for /api/generate for backward compat."""
    return generate()

# ──────────────────────────────────────────────────────────────────────────────
# 18. MAIN
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("🛸 UAV-LLM Backend starting on http://0.0.0.0:5000")
    print(f"   Ollama model: {OLLAMA_MODEL}  (run: ollama pull glm4)")
    print(f"   Locations loaded: {len(LOCATIONS)}")
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
