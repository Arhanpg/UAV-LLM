#!/usr/bin/env python3
"""
UAV-LLM v3.0 — Real-World Semantic Multi-Commodity UAV Delivery
FastAPI backend: MPDD + HNP + SMT-style verification + Ollama GLM integration
Real GPS coordinates (Bengaluru default), OSM-ready, full 3D altitude planning
"""

import math, time, itertools, random, json, os
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import httpx

app = FastAPI(title="UAV-LLM Real-World System", version="3.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

# ─── Constants ────────────────────────────────────────────────────────────────
CLASSES = ["PHARMA","FOOD","ELECTRONICS","FLAMMABLE","OXIDIZER","CRYOGENIC","GENERAL"]
HAZARD_CLASSES = {"FLAMMABLE","OXIDIZER","CRYOGENIC"}
FIXED_INCOMPAT = [
    ("FLAMMABLE","OXIDIZER"),("CRYOGENIC","ELECTRONICS"),
    ("FLAMMABLE","PHARMA"),("OXIDIZER","PHARMA"),("CRYOGENIC","FOOD"),
    ("FLAMMABLE","FOOD"),("OXIDIZER","FOOD")
]
PENALTIES = {"compat":220.0,"geo":160.0,"payload":300.0,"precedence":220.0,"missed":600.0}
ALPHA_OBJ = {"distance":1.0,"lateness":1.8,"noise":0.55,"energy":0.08}

OLLAMA_URL   = os.getenv("OLLAMA_URL",  "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL","glm4")

UAV_SPEED   = 15.0   # m/s
ROTOR_K     = 0.04   # energy coefficient per kg
MIN_ALT     = 30.0   # minimum flight altitude (m)
CLEARANCE   = 10.0   # clearance above buildings (m)
EARTH_R     = 6371000.0  # metres

# ─── Bengaluru Real-World Locations ──────────────────────────────────────────
# Format: (name, lat, lon, building_height_m, category)
BLR_LOCATIONS = [
    # Index 0 = depot
    ("SDM Hospital",          13.0012, 77.5880, 20.0,  "hospital"),
    ("Urban Oasis Mall",      13.0155, 77.6101, 45.0,  "mall"),
    ("Cubbon Park",           12.9763, 77.5929, 5.0,   "park"),
    ("Lal Bagh Botanical",    12.9508, 77.5848, 3.0,   "park"),
    ("KR Market",             12.9716, 77.5764, 12.0,  "market"),
    ("MG Road Metro",         12.9754, 77.6078, 8.0,   "transit"),
    ("Manipal Hospital",      12.9566, 77.5934, 35.0,  "hospital"),
    ("Indiranagar 100ft Rd",  12.9784, 77.6408, 18.0,  "commercial"),
    ("Koramangala Forum",     12.9352, 77.6100, 50.0,  "mall"),
    ("Whitefield IT Park",    12.9698, 77.7499, 60.0,  "office"),
    ("Yelahanka Air Base",    13.1290, 77.6065, 8.0,   "airbase"),
    ("Hebbal Flyover",        13.0350, 77.5970, 10.0,  "transit"),
    ("Jayanagar 4th Block",   12.9258, 77.5839, 15.0,  "residential"),
    ("Rajajinagar",           12.9914, 77.5530, 12.0,  "residential"),
    ("Electronic City",       12.8458, 77.6603, 55.0,  "office"),
    ("Vidhana Soudha",        12.9796, 77.5906, 60.0,  "govt"),
    ("Ulsoor Lake",           12.9786, 77.6200, 4.0,   "park"),
    ("Richmond Road",         12.9626, 77.5986, 20.0,  "commercial"),
    ("Banashankari Temple",   12.9255, 77.5468, 10.0,  "religious"),
    ("Marathahalli Bridge",   12.9591, 77.7014, 8.0,   "transit"),
]

# ─── Geo helpers ──────────────────────────────────────────────────────────────
def haversine(lat1, lon1, lat2, lon2) -> float:
    """Distance in metres between two GPS coordinates."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return 2 * EARTH_R * math.asin(math.sqrt(a))

def lat_lon_to_xy(lat, lon, origin_lat, origin_lon) -> Tuple[float, float]:
    """Convert GPS to local XY metres (equirectangular)."""
    x = math.radians(lon - origin_lon) * math.cos(math.radians(origin_lat)) * EARTH_R
    y = math.radians(lat - origin_lat) * EARTH_R
    return x, y

def dist_2d(ax, ay, bx, by) -> float:
    return math.hypot(ax - bx, ay - by)

def dist_3d(ax, ay, az, bx, by, bz) -> float:
    return math.sqrt((ax-bx)**2 + (ay-by)**2 + (az-bz)**2)

# ─── Data classes ─────────────────────────────────────────────────────────────
@dataclass
class CityNode:
    idx: int
    lat: float
    lon: float
    x: float              # local metres
    y: float
    building_height: float
    label: str
    category: str
    is_depot: bool = False
    pickups: List[dict] = field(default_factory=list)
    drops:   List[dict] = field(default_factory=list)

@dataclass
class Package:
    idx: int
    pickup_loc: int
    delivery_loc: int
    weight: float
    kappa: str
    deadline: float       # seconds
    priority: float
    temp_required: bool
    description: str = ""
    nlp_raw: str = ""

@dataclass
class GeoZone:
    x: float; y: float
    radius: float
    kind: str             # 'nofly' | 'noise' | 'residential'
    label: str = ""
    alt_ceiling: float = 9999.0   # UAV must fly ABOVE this alt in zone

@dataclass
class FlightStep:
    step: int
    node_idx: int
    x: float; y: float
    lat: float; lon: float
    altitude: float
    role: str             # DEPOT | P | D
    req_idx: int
    node_label: str
    dist_from_prev: float
    payload: float
    elapsed_s: float
    algo_decision: dict

# ─── Compatibility graph ──────────────────────────────────────────────────────
def build_compat(density: float, seed: int) -> Dict[Tuple, bool]:
    rng = np.random.default_rng(seed)
    G = {(a,b): True for a in CLASSES for b in CLASSES}
    for a,b in FIXED_INCOMPAT:
        G[(a,b)] = G[(b,a)] = False
    pairs = [(a,b) for i,a in enumerate(CLASSES) for b in CLASSES[i+1:]]
    for a,b in pairs:
        if G[(a,b)] and rng.random() < density:
            G[(a,b)] = G[(b,a)] = False
    return G

def clique_ok(classes: list, G: dict) -> bool:
    return all(G.get((a,b), True) for a,b in itertools.combinations(classes, 2))

# ─── Zone geometry ────────────────────────────────────────────────────────────
def seg_hits_zone(ax, ay, bx, by, z: GeoZone) -> bool:
    cx, cy = z.x, z.y
    abx, aby = bx-ax, by-ay
    denom = abx*abx + aby*aby
    if denom < 1e-12:
        return (ax-cx)**2 + (ay-cy)**2 <= z.radius**2
    t = max(0.0, min(1.0, ((cx-ax)*abx+(cy-ay)*aby)/denom))
    px, py = ax+t*abx, ay+t*aby
    return (px-cx)**2 + (py-cy)**2 <= z.radius**2

def geo_penalty(ax, ay, bx, by, gzones: List[GeoZone]) -> float:
    return sum(dist_2d(ax,ay,bx,by) for z in gzones if seg_hits_zone(ax,ay,bx,by,z))

# ─── Altitude planning ───────────────────────────────────────────────────────
def compute_altitude(ax, ay, bx, by, city_nodes: List[CityNode]) -> float:
    """Find max building height along segment + clearance."""
    x0, x1 = min(ax,bx)-20, max(ax,bx)+20
    y0, y1 = min(ay,by)-20, max(ay,by)+20
    max_bh = max(
        (n.building_height for n in city_nodes
         if x0 <= n.x <= x1 and y0 <= n.y <= y1),
        default=0.0
    )
    return max(MIN_ALT, max_bh + CLEARANCE)

# ─── Energy model ────────────────────────────────────────────────────────────
def energy_3d(d3: float, payload: float, wind_comp: float = 0.0) -> float:
    """Energy proxy: distance × (1 + rotor_k × payload) + wind penalty."""
    return d3 * (1.0 + ROTOR_K * payload) + wind_comp

def wind_penalty(ax, ay, bx, by, wind_dir: float = 45.0, wind_spd: float = 5.0) -> float:
    dx, dy = bx-ax, by-ay
    angle = math.degrees(math.atan2(dy, dx)) % 360
    diff  = abs(angle - wind_dir) % 360
    if diff > 180: diff = 360 - diff
    hw = math.cos(math.radians(diff))
    return dist_2d(ax,ay,bx,by) * max(0, hw) * wind_spd * 0.002

# ─── Node role ───────────────────────────────────────────────────────────────
def node_role(node: int, n: int) -> Tuple[str, int]:
    if 1 <= node <= n:        return "P", node - 1
    if n+1 <= node <= 2*n:    return "D", node - (n+1)
    return "DEPOT", -1

# ─── Full route evaluator ────────────────────────────────────────────────────
def evaluate(traj_xy, city_nodes, packages, route, G, gzones, nzones,
             synth=None, W=20.0, wind_dir=45.0):
    n = len(packages)
    onboard=set(); delivered=set(); y=0.0; t=0.0
    dist=en=noise=lateness=0.0
    cv=gv=pv=rv=0; seen=set()
    depot_ok = 1 if (route and route[0]==0 and route[-1]==2*n+1) else 0
    for s in range(len(route)-1):
        u, v = route[s], route[s+1]
        ax, ay = traj_xy[u]; bx, by = traj_xy[v]
        alt = compute_altitude(ax,ay,bx,by,city_nodes)
        seg2d = dist_2d(ax,ay,bx,by)
        seg3d = math.sqrt(seg2d**2 + 5.0**2)  # small vertical component
        dist  += seg2d
        wp     = wind_penalty(ax,ay,bx,by,wind_dir)
        en    += energy_3d(seg3d, y, wp)
        noise += sum(seg2d for z in nzones if seg_hits_zone(ax,ay,bx,by,z))
        if any(seg_hits_zone(ax,ay,bx,by,z) for z in gzones): gv += 1
        t += seg2d / UAV_SPEED
        tp, rid = node_role(v, n)
        if tp in {"P","D"}:
            if v in seen: rv += 1
            seen.add(v)
        if tp == "P":
            pkg = packages[rid]; y += pkg.weight; onboard.add(rid)
        elif tp == "D":
            pkg = packages[rid]
            if rid not in onboard: rv += 1
            else:
                y -= pkg.weight; onboard.remove(rid)
                delivered.add(rid)
                lateness += max(0, t - pkg.deadline) * pkg.priority
        if y < -1e-6 or y - W > 1e-6: pv += 1
        kk = [(synth[i] if synth else packages[i].kappa) for i in onboard]
        if not clique_ok(kk, G): cv += 1
    expected = set(range(1, 2*n+1))
    missed = len(expected - seen) + len(seen - expected) + rv + (0 if depot_ok else 1)
    total_viol = cv + gv + pv + rv + missed
    cost = (
        ALPHA_OBJ["distance"]*dist + ALPHA_OBJ["lateness"]*lateness +
        ALPHA_OBJ["noise"]*noise + ALPHA_OBJ["energy"]*en +
        PENALTIES["compat"]*cv + PENALTIES["geo"]*gv +
        PENALTIES["payload"]*pv + PENALTIES["precedence"]*rv +
        PENALTIES["missed"]*missed
    )
    return {
        "cost":cost, "dist":round(dist,2), "lateness":round(lateness,3),
        "noise":round(noise,2), "energy":round(en,2),
        "cv":cv, "gv":gv, "pv":pv, "rv":rv, "missed":missed,
        "viol":total_viol, "feasible":total_viol==0,
        "delivered":len(delivered), "n":n, "time_s":round(t,1),
        "battery_pct": round(max(0, 100 - en/50), 1)
    }

# ─── Feasible candidates (MPDD constraint 1d) ─────────────────────────────────
def feasible_cands(packages, U, onboard, y, synth, G, W, compat_check):
    n = len(packages); C = []; active = [synth[i] for i in onboard]
    for node in U:
        tp, rid = node_role(node, n)
        if tp == "P":
            pkg = packages[rid]
            if y + pkg.weight <= W + 1e-9:
                kk = synth[rid]
                if (not compat_check) or clique_ok(active+[kk], G):
                    C.append(node)
        elif tp == "D" and rid in onboard:
            C.append(node)
    return C

# ─── HNP scoring (Eq 6 extended with semantic terms) ─────────────────────────
def blocks_future(rid, onboard, U, synth, packages, G, n):
    if rid not in onboard: return 0
    before = [synth[i] for i in onboard]
    after  = [synth[i] for i in onboard if i != rid]
    for uk in U:
        utp, uid = node_role(uk, n)
        if utp == "P":
            ck = synth[uid]
            if not clique_ok(before+[ck], G) and clique_ok(after+[ck], G):
                return 1
    return 0

def hnp_scores(traj_xy, packages, cands, cur, onboard, U, synth, G,
               gzones, t, n, beta=45.0, gamma_geo=1.5, gamma_dl=120.0):
    cpos = traj_xy[cur]
    dists = {j: max(1e-6, dist_2d(*cpos, *traj_xy[j])) for j in cands}
    dmin  = min(dists.values())
    scores = {}
    for j in cands:
        tp, rid = node_role(j, n)
        if rid < 0: continue
        pkg = packages[rid]; d = dists[j]
        dl  = gamma_dl * pkg.priority / max(1.0, pkg.deadline - t) if tp == "D" else 0
        geo = gamma_geo * geo_penalty(*cpos, *traj_xy[j], gzones)
        blk = beta * blocks_future(rid, onboard, U, synth, packages, G, n) if tp == "D" else 0
        scores[j] = 0.55*(dmin/d) + 0.45*pkg.weight + blk + dl - geo
    return scores

def mpdd_scores(traj_xy, packages, cands, cur, n):
    cpos  = traj_xy[cur]
    dists = {j: max(1e-6, dist_2d(*cpos, *traj_xy[j])) for j in cands}
    dmin  = min(dists.values())
    vals  = {j: packages[node_role(j,n)[1]].weight
             if node_role(j,n)[1] >= 0 else 1.0 for j in cands}
    vm    = max(vals.values(), default=1.0)
    return {j: 0.6*(dmin/dists[j]) + 0.4*(vals[j]/vm) for j in cands}

def nn_scores(traj_xy, cands, cur):
    cpos  = traj_xy[cur]
    dists = {j: max(1e-6, dist_2d(*cpos, *traj_xy[j])) for j in cands}
    dmin  = min(dists.values())
    return {j: dmin/dists[j] for j in cands}

# ─── Route builder (Phase 1 greedy) ──────────────────────────────────────────
def build_route(packages, traj_xy, synth, G, gzones, W, compat_check, score_fn, label):
    n = len(packages); start = 0; end = 2*n+1
    route = [start]; U = set(range(1, 2*n+1))
    onboard = set(); y = 0.0; t = 0.0; log = []
    safety = 0
    while U and safety < 20*(2*n+2):
        safety += 1
        C = feasible_cands(packages, U, onboard, y, synth, G, W, compat_check)
        if not C:
            unpicked = [j for j in U if node_role(j,n)[0]=="P"]
            if not unpicked: break
            C = unpicked
        if not C: break
        sc     = score_fn(C, route[-1], onboard, U, t)
        jstar  = max(C, key=lambda j: sc.get(j, 0))
        prev   = route[-1]
        seg    = dist_2d(*traj_xy[prev], *traj_xy[jstar])
        log.append({
            "algo":label, "node":jstar, "score":round(sc.get(jstar,0),3),
            "candidates":len(C), "onboard":len(onboard), "payload":round(y,2),
            "dist_seg":round(seg,1)
        })
        route.append(jstar)
        t += seg / UAV_SPEED
        tp, rid = node_role(jstar, n)
        if tp == "P":   onboard.add(rid);    y += packages[rid].weight
        elif tp == "D" and rid in onboard:
            onboard.remove(rid); y -= packages[rid].weight
        U.discard(jstar)
    if route[-1] != end: route.append(end)
    return route, log

# ─── Trajectory refinement (Phase 2 TSP-approx via 2-opt swap) ───────────────
def refine(packages, traj_xy, route, synth, G, W, gzones, max_passes=3):
    best = route[:]; n = len(packages)
    def pick_pos(rt): return [i for i,nd in enumerate(rt) if node_role(nd,n)[0]=="P"]
    for _ in range(max_passes):
        improved = False
        anchors = [0] + pick_pos(best) + [len(best)-1]
        for ai in range(len(anchors)-1):
            lo, hi = anchors[ai], anchors[ai+1]
            if hi - lo <= 3: continue
            seg  = best[lo+1:hi]
            dloc = [k for k,nd in enumerate(seg) if node_role(nd,n)[0]=="D"]
            if len(dloc) < 2: continue
            base = evaluate(traj_xy,[],packages,best,G,[],[],synth,W)["dist"]
            for xi in range(len(dloc)):
                for yi in range(xi+1, len(dloc)):
                    cand = best[:]
                    ix, iy = lo+1+dloc[xi], lo+1+dloc[yi]
                    cand[ix], cand[iy] = cand[iy], cand[ix]
                    m = evaluate(traj_xy,[],packages,cand,G,[],[],synth,W)
                    if m["dist"] < base-1e-9 and m["pv"]==0 and m["rv"]==0:
                        best = cand; improved = True; break
                if improved: break
            if improved: break
        if not improved: break
    return best

# ─── SMT-style verified synthesis ────────────────────────────────────────────
def verified_synthesis(packages, seed, llm_error, Rmax=3):
    """
    Simulates LLM constraint synthesis with SMT verifier.
    Ψ: Σ* → F_FOL  (Eq 1 from formulation paper)
    V: F_FOL → {0,1}  (verifier)
    """
    rng = np.random.default_rng(seed)
    synth = {}; verification_log = []
    for pkg in packages:
        accepted = None; recovered = False; attempts = []
        for attempt in range(Rmax):
            # Simulate LLM prediction with error rate
            p_err = min(0.60, llm_error)
            if rng.random() > p_err:
                pred = pkg.kappa
            else:
                pred = rng.choice([c for c in CLASSES if c != pkg.kappa]).item()
            # SMT verifier: false-accept 2%, false-reject 1%
            if pred == pkg.kappa:
                v_ok = rng.random() > 0.01
            else:
                v_ok = rng.random() < 0.02
            attempts.append({"pred":pred,"verified":bool(v_ok)})
            if v_ok: accepted = pred; break
        if accepted is None: accepted = pkg.kappa; recovered = True
        synth[pkg.idx] = accepted
        verification_log.append({
            "req":pkg.idx,"true_kappa":pkg.kappa,"synth_kappa":accepted,
            "verified":accepted==pkg.kappa,"recovered":recovered,
            "attempts":attempts
        })
    return synth, verification_log

# ─── Run all algorithms ───────────────────────────────────────────────────────
def run_all_algos(packages, traj_xy, city_nodes, G, gzones, nzones, W_cap,
                  seed, wind_dir=45.0, llm_error=0.10):
    synth_true = {p.idx: p.kappa for p in packages}
    synth_llm, verif_log = verified_synthesis(packages, seed+1, llm_error)
    rng = np.random.default_rng(seed+2)
    synth_noisy = {
        p.idx: (rng.choice([c for c in CLASSES if c!=p.kappa]).item()
                if rng.random() < llm_error else p.kappa)
        for p in packages
    }
    n = len(packages)
    results = {}

    def _run(label, synth, compat_check, score_type, do_refine):
        if score_type == "hnp":
            def sf(C,cur,ob,U,t):
                return hnp_scores(traj_xy,packages,C,cur,ob,U,synth,G,gzones,t,n)
        elif score_type == "mpdd":
            def sf(C,cur,ob,U,t):
                return mpdd_scores(traj_xy,packages,C,cur,n)
        else:
            def sf(C,cur,ob,U,t):
                return nn_scores(traj_xy,C,cur)
        t0 = time.perf_counter()
        r, log = build_route(packages,traj_xy,synth,G,gzones,W_cap,compat_check,sf,label)
        if do_refine:
            r = refine(packages,traj_xy,r,synth,G,W_cap,gzones)
        elapsed = time.perf_counter() - t0
        m = evaluate(traj_xy,city_nodes,packages,r,G,gzones,nzones,synth,W_cap,wind_dir)
        m["runtime"] = round(elapsed,4)
        return {"route":r,"log":log,"metrics":m,
                "synth":synth, "verif_log":verif_log if label=="HNP" else []}

    results["HNP"]          = _run("HNP",          synth_llm,  True,  "hnp",  True)
    results["MPDD"]         = _run("MPDD",         synth_true, False, "mpdd", False)
    results["NN-PDP"]       = _run("NN-PDP",       synth_true, False, "nn",   False)
    results["HNP-NoVerify"] = _run("HNP-NoVerify", synth_noisy,True,  "hnp",  True)
    results["HNP-NoCompat"] = _run("HNP-NoCompat", synth_llm,  False, "hnp",  True)
    results["HNP-NoRefine"] = _run("HNP-NoRefine", synth_llm,  True,  "hnp",  False)
    return results

# ─── Flight path builder (3D steps) ──────────────────────────────────────────
def build_flight_path(route, traj_xy, traj_gps, city_nodes, packages):
    n   = len(packages)
    steps = []; y = 0.0; t = 0.0
    for si, nd in enumerate(route):
        if si == 0:
            steps.append({
                "step":0, "node":nd,
                "x":traj_xy[nd][0], "y":traj_xy[nd][1],
                "lat":traj_gps[nd][0], "lon":traj_gps[nd][1],
                "alt":MIN_ALT, "role":"DEPOT", "req":-1,
                "label":city_nodes[0].label,
                "dist":0.0, "payload":0.0, "time":0.0,
                "algo_info":{"action":"TAKEOFF","payload":0}
            })
            continue
        prev = route[si-1]
        ax,ay = traj_xy[prev]; bx,by = traj_xy[nd]
        alt   = compute_altitude(ax,ay,bx,by,city_nodes)
        seg2d = dist_2d(ax,ay,bx,by)
        t    += seg2d / UAV_SPEED
        tp, rid = node_role(nd, n)
        if tp == "P":
            y += packages[rid].weight
            action = f"PICKUP pkg#{rid} ({packages[rid].kappa})"
            nd_label = city_nodes[packages[rid].pickup_loc].label if packages[rid].pickup_loc < len(city_nodes) else f"Node {nd}"
        elif tp == "D":
            if rid < len(packages): y = max(0, y - packages[rid].weight)
            action = f"DELIVER pkg#{rid}"
            nd_label = city_nodes[packages[rid].delivery_loc].label if rid < len(packages) and packages[rid].delivery_loc < len(city_nodes) else f"Node {nd}"
        else:
            action = "RETURN"; nd_label = city_nodes[0].label
        steps.append({
            "step":si, "node":nd,
            "x":traj_xy[nd][0], "y":traj_xy[nd][1],
            "lat":traj_gps[nd][0], "lon":traj_gps[nd][1],
            "alt":round(alt,1), "role":tp, "req":rid,
            "label":nd_label,
            "dist":round(seg2d,1), "payload":round(y,2),
            "time":round(t,1),
            "algo_info":{"action":action, "payload":round(y,2), "altitude":round(alt,1)}
        })
    return steps

# ─── World generation (real Bengaluru coords) ─────────────────────────────────
def generate_world(loc_indices: List[int], pkg_requests: List[dict],
                   seed: int, incompat_density: float, n_gfz: int,
                   deadline_tight: float, hazard_mix: float, cap_ratio: float):
    """
    loc_indices: list of indices into BLR_LOCATIONS
    pkg_requests: list of {pickup_name, delivery_name, kappa?, weight?, description?}
    """
    rng = np.random.default_rng(seed)

    # Build city nodes
    if not loc_indices or len(loc_indices) < 2:
        loc_indices = list(range(min(10, len(BLR_LOCATIONS))))

    # Depot is first location
    depot_data = BLR_LOCATIONS[loc_indices[0]]
    origin_lat, origin_lon = depot_data[1], depot_data[2]

    city: List[CityNode] = []
    for i, li in enumerate(loc_indices):
        ld = BLR_LOCATIONS[li]
        x, y = lat_lon_to_xy(ld[1], ld[2], origin_lat, origin_lon)
        city.append(CityNode(
            idx=i, lat=ld[1], lon=ld[2], x=x, y=y,
            building_height=ld[3], label=ld[0], category=ld[4],
            is_depot=(i==0)
        ))

    G = build_compat(incompat_density, seed)
    PKG_LABELS = {
        "PHARMA":"Insulin","FOOD":"Food Box","ELECTRONICS":"Laptop",
        "FLAMMABLE":"Fuel Can","OXIDIZER":"O₂ Tank","CRYOGENIC":"Cryo Sample",
        "GENERAL":"Package"
    }

    def sample_kappa():
        if rng.random() < hazard_mix:
            return rng.choice(["PHARMA","FLAMMABLE","OXIDIZER","CRYOGENIC","ELECTRONICS"],
                              p=[0.30,0.22,0.18,0.15,0.15]).item()
        return rng.choice(CLASSES, p=[0.16,0.18,0.16,0.08,0.06,0.06,0.30]).item()

    packages: List[Package] = []
    total_w = 0.0

    # Use provided requests or auto-generate
    if pkg_requests:
        for i, req in enumerate(pkg_requests):
            # Find pickup/delivery node by name
            pu_name = req.get("pickup_name", "")
            dl_name = req.get("delivery_name", "")
            pu_idx  = next((c.idx for c in city if pu_name.lower() in c.label.lower()), 0)
            dl_idx  = next((c.idx for c in city if dl_name.lower() in c.label.lower()),
                           min(1, len(city)-1))
            kappa   = req.get("kappa") or sample_kappa()
            weight  = float(req.get("weight", rng.uniform(1.0, 5.0)))
            total_w += weight
            pu_c = city[pu_idx]; dl_c = city[dl_idx]
            d2d  = dist_2d(pu_c.x, pu_c.y, dl_c.x, dl_c.y)
            dep_leg = dist_2d(city[0].x, city[0].y, pu_c.x, pu_c.y) + d2d
            slack = float(rng.uniform(30,100)) * (1.05 - deadline_tight)
            dl    = dep_leg/UAV_SPEED + slack + float(rng.uniform(0,20))
            pr    = 1.8 if kappa=="PHARMA" else (1.4 if kappa in HAZARD_CLASSES else 1.0)
            desc  = req.get("description") or f"{PKG_LABELS.get(kappa,'Pkg')} · {pu_c.label} → {dl_c.label}"
            packages.append(Package(i, pu_idx, dl_idx, weight, kappa, dl, pr,
                                    kappa in {"PHARMA","FOOD","CRYOGENIC"}, desc))
            city[pu_idx].pickups.append({"req":i,"kappa":kappa,"w":round(weight,2),"label":PKG_LABELS.get(kappa,"Pkg")})
            city[dl_idx].drops.append(  {"req":i,"kappa":kappa,"w":round(weight,2),"label":PKG_LABELS.get(kappa,"Pkg")})
    else:
        n_auto = max(3, min(8, len(city)-1))
        for i in range(n_auto):
            kappa  = sample_kappa()
            pi_idx = int(rng.integers(1, len(city)))
            di_idx = int(rng.integers(1, len(city)))
            while di_idx == pi_idx: di_idx = int(rng.integers(1, len(city)))
            weight  = float(rng.uniform(1.0, 6.0)); total_w += weight
            pu_c    = city[pi_idx]; dl_c = city[di_idx]
            d2d     = dist_2d(pu_c.x, pu_c.y, dl_c.x, dl_c.y)
            dep_leg = dist_2d(city[0].x, city[0].y, pu_c.x, pu_c.y) + d2d
            slack   = float(rng.uniform(30,100)) * (1.05 - deadline_tight)
            dl_t    = dep_leg/UAV_SPEED + slack + float(rng.uniform(0,20))
            pr      = 1.8 if kappa=="PHARMA" else (1.4 if kappa in HAZARD_CLASSES else 1.0)
            desc    = f"{PKG_LABELS.get(kappa,'Pkg')} · {pu_c.label} → {dl_c.label}"
            packages.append(Package(i, pi_idx, di_idx, weight, kappa, dl_t, pr,
                                    kappa in {"PHARMA","FOOD","CRYOGENIC"}, desc))
            city[pi_idx].pickups.append({"req":i,"kappa":kappa,"w":round(weight,2),"label":PKG_LABELS.get(kappa,"Pkg")})
            city[di_idx].drops.append(  {"req":i,"kappa":kappa,"w":round(weight,2),"label":PKG_LABELS.get(kappa,"Pkg")})

    W_cap = max(8.0, cap_ratio * total_w)

    # Geo zones: place near tall buildings or random
    tall = sorted(city, key=lambda c: c.building_height, reverse=True)
    gzones: List[GeoZone] = []
    nzones: List[GeoZone] = []
    for i in range(min(n_gfz, len(tall))):
        c = tall[i]
        gzones.append(GeoZone(c.x + float(rng.uniform(-30,30)),
                               c.y + float(rng.uniform(-30,30)),
                               float(rng.uniform(60,150)), "nofly",
                               f"No-Fly near {c.label}"))
        nzones.append(GeoZone(c.x + float(rng.uniform(-50,50)),
                               c.y + float(rng.uniform(-50,50)),
                               float(rng.uniform(80,200)), "noise",
                               f"Noise Zone {i+1}"))

    # Build trajectory arrays
    # traj_xy[0] = depot, [1..n] = pickups, [n+1..2n] = deliveries, [2n+1] = depot
    traj_xy  = [(city[0].x, city[0].y)]
    traj_gps = [(city[0].lat, city[0].lon)]
    for p in packages:
        cx = city[p.pickup_loc]
        traj_xy.append((cx.x, cx.y))
        traj_gps.append((cx.lat, cx.lon))
    for p in packages:
        cx = city[p.delivery_loc]
        traj_xy.append((cx.x, cx.y))
        traj_gps.append((cx.lat, cx.lon))
    traj_xy.append((city[0].x, city[0].y))
    traj_gps.append((city[0].lat, city[0].lon))

    return city, packages, G, gzones, nzones, W_cap, traj_xy, traj_gps

# ─── Ollama LLM calls ─────────────────────────────────────────────────────────
async def ollama_chat(prompt: str, model: str = None) -> str:
    mdl = model or OLLAMA_MODEL
    try:
        async with httpx.AsyncClient(timeout=30.0) as cli:
            r = await cli.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model":mdl,"prompt":prompt,"stream":False,
                      "options":{"temperature":0.1,"num_predict":800}}
            )
            if r.status_code == 200:
                return r.json().get("response", "")
    except Exception as e:
        return f"[LLM offline — {e}]"
    return ""

async def llm_parse_nl_instruction(instruction: str, city_labels: List[str],
                                    classes: List[str]) -> dict:
    prompt = f"""You are a UAV mission planner AI. Parse the natural language instruction.

Available locations: {city_labels}
Cargo classes: {classes}
Hazardous classes (cannot mix): FLAMMABLE+OXIDIZER, FLAMMABLE+PHARMA, CRYOGENIC+FOOD

Instruction: \"{instruction}\"

Output ONLY valid JSON:
{{"actions": [
  {{"type": "PICKUP|DELIVER|REROUTE|ABORT|EMERGENCY_RETURN|ALTITUDE_CHANGE|STATUS",
    "location": "location name or null",
    "package_kappa": "PHARMA|FOOD|etc or null",
    "weight_kg": 2.5,
    "new_altitude_m": null,
    "reason": "brief reason",
    "deadline_minutes": null,
    "priority": 1.0}}
],
"constraints_detected": ["cold-chain","no-fly","deadline"],
"semantic_cost_impact": "LOW|MEDIUM|HIGH",
"llm_confidence": 0.9
}}"""
    raw = await ollama_chat(prompt)
    try:
        s = raw.find("{"); e = raw.rfind("}")+1
        if s >= 0 and e > s:
            return json.loads(raw[s:e])
    except:
        pass
    # Fallback heuristic parse
    dl = instruction.lower()
    kappa = "GENERAL"
    for kw, k in [("insulin","PHARMA"),("pharma","PHARMA"),("medicine","PHARMA"),
                   ("fuel","FLAMMABLE"),("oxygen","OXIDIZER"),("cryo","CRYOGENIC"),
                   ("food","FOOD"),("laptop","ELECTRONICS")]:
        if kw in dl: kappa = k; break
    action = "STATUS"
    if any(w in dl for w in ["pickup","pick up","collect","grab"]): action = "PICKUP"
    elif any(w in dl for w in ["deliver","drop","bring"]): action = "DELIVER"
    elif any(w in dl for w in ["return","emergency","abort"]): action = "EMERGENCY_RETURN"
    elif any(w in dl for w in ["reroute","avoid","go to"]): action = "REROUTE"
    return {"actions":[{"type":action,"location":None,"package_kappa":kappa,
                         "reason":"heuristic fallback","priority":1.0}],
            "constraints_detected":[],"semantic_cost_impact":"UNKNOWN","llm_confidence":0.3}

async def llm_initial_mission_plan(instruction: str, city_labels: List[str]) -> dict:
    prompt = f"""You are a UAV mission planner. Generate a structured mission plan.

Depot (start/end): {city_labels[0] if city_labels else 'Depot'}
Available waypoints: {city_labels[1:]}

Mission instruction: \"{instruction}\"

Output ONLY valid JSON:
{{"mission_name": "short name",
  "waypoints": [
    {{"location": "exact location name", "action": "PICKUP|DELIVER|STOP",
      "package_description": "what item", "weight_kg": 2.0,
      "kappa": "PHARMA|FOOD|ELECTRONICS|FLAMMABLE|OXIDIZER|CRYOGENIC|GENERAL",
      "deadline_minutes": 30}}
  ],
  "total_estimated_time_minutes": 45,
  "risk_flags": ["incompatible cargo warning"],
  "llm_reasoning": "brief explanation"
}}"""
    raw = await ollama_chat(prompt)
    try:
        s = raw.find("{"); e = raw.rfind("}")+1
        if s >= 0 and e > s:
            return json.loads(raw[s:e])
    except:
        pass
    return {"mission_name":"Auto Plan","waypoints":[],
            "risk_flags":[],"llm_reasoning":raw[:300] if raw else "No response"}

# ─── Session store ────────────────────────────────────────────────────────────
SESSIONS: Dict[str, dict] = {}

# ─── API models ───────────────────────────────────────────────────────────────
class GenConfig(BaseModel):
    loc_indices:       List[int]   = list(range(10))
    pkg_requests:      List[dict]  = []
    seed:              int         = 42
    incompat_density:  float       = 0.25
    n_gfz:             int         = 3
    deadline_tight:    float       = 0.65
    hazard_mix:        float       = 0.50
    cap_ratio:         float       = 0.35
    wind_dir:          float       = 45.0
    llm_error:         float       = 0.10

class NLInstructionReq(BaseModel):
    instruction: str
    session_id:  str = "default"
    phase:       str = "midflight"   # 'initial' | 'midflight'

class ReplanReq(BaseModel):
    session_id:  str
    disruption:  dict

# ─── Routes ───────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return FileResponse("index.html")

@app.post("/api/generate")
async def generate(cfg: GenConfig):
    city, pkgs, G, gzones, nzones, W_cap, traj_xy, traj_gps = generate_world(
        cfg.loc_indices, cfg.pkg_requests, cfg.seed,
        cfg.incompat_density, cfg.n_gfz, cfg.deadline_tight,
        cfg.hazard_mix, cfg.cap_ratio
    )
    results = run_all_algos(
        pkgs, traj_xy, city, G, gzones, nzones, W_cap,
        cfg.seed, cfg.wind_dir, cfg.llm_error
    )
    sid = f"s{cfg.seed}_{int(time.time()*1000)%100000}"
    SESSIONS[sid] = dict(
        city=city, pkgs=pkgs, G=G, gzones=gzones, nzones=nzones,
        W_cap=W_cap, traj_xy=traj_xy, traj_gps=traj_gps,
        results=results, wind_dir=cfg.wind_dir
    )

    hnp_route = results["HNP"]["route"]
    flight_path = build_flight_path(hnp_route, traj_xy, traj_gps, city, pkgs)
    incompat_pairs = [[a,b] for (a,b),ok in G.items() if not ok and a < b]

    return {
        "session_id": sid,
        "origin": {"lat": city[0].lat, "lon": city[0].lon},
        "city": [{
            "idx":n.idx, "lat":n.lat, "lon":n.lon,
            "x":round(n.x,1), "y":round(n.y,1),
            "bh":n.building_height, "label":n.label,
            "category":n.category, "depot":n.is_depot,
            "pickups":n.pickups, "drops":n.drops
        } for n in city],
        "packages": [{
            "idx":p.idx, "pickup":p.pickup_loc, "delivery":p.delivery_loc,
            "weight":round(p.weight,2), "kappa":p.kappa,
            "deadline":round(p.deadline,1), "priority":p.priority,
            "temp":p.temp_required, "desc":p.description
        } for p in pkgs],
        "gzones": [{"x":z.x,"y":z.y,"r":z.radius,"kind":z.kind,"label":z.label} for z in gzones],
        "nzones": [{"x":z.x,"y":z.y,"r":z.radius,"kind":z.kind,"label":z.label} for z in nzones],
        "W_cap": round(W_cap,2),
        "traj_xy":  traj_xy,
        "traj_gps": traj_gps,
        "results": {
            k: {"route":v["route"],"metrics":v["metrics"],
                "log":v["log"][:40], "verif_log":v.get("verif_log",[])[:20]}
            for k,v in results.items()
        },
        "flight_path": flight_path,
        "incompat_pairs": incompat_pairs,
        "classes": CLASSES,
        "blr_locations": [
            {"idx":i,"name":l[0],"lat":l[1],"lon":l[2],"bh":l[3],"cat":l[4]}
            for i,l in enumerate(BLR_LOCATIONS)
        ]
    }

@app.post("/api/llm/instruction")
async def nl_instruction(req: NLInstructionReq):
    sess = SESSIONS.get(req.session_id, {})
    city = sess.get("city", [])
    city_labels = [c.label for c in city] if city else []

    if req.phase == "initial":
        result = await llm_initial_mission_plan(req.instruction, city_labels)
    else:
        pkgs   = sess.get("pkgs", [])
        state  = {
            "onboard": [p.kappa for p in pkgs],
            "payload": sum(p.weight for p in pkgs),
        }
        result = await llm_parse_nl_instruction(req.instruction, city_labels, CLASSES)

    return {
        "instruction": req.instruction,
        "phase": req.phase,
        "result": result,
        "ollama_model": OLLAMA_MODEL
    }

@app.post("/api/replan")
async def replan(req: ReplanReq):
    sess = SESSIONS.get(req.session_id)
    if not sess: raise HTTPException(404, "Session not found")
    disruption = req.disruption
    if disruption.get("type") == "nofly":
        sess["gzones"].append(GeoZone(
            disruption["x"], disruption["y"],
            disruption.get("r", 120), "nofly", "Emergency No-Fly"
        ))
    pkgs   = sess["pkgs"]; traj_xy = sess["traj_xy"]
    G      = sess["G"];    gzones  = sess["gzones"]
    nzones = sess["nzones"]; W_cap = sess["W_cap"]
    city   = sess["city"];   traj_gps = sess["traj_gps"]
    synth  = {p.idx: p.kappa for p in pkgs}
    n      = len(pkgs)
    def sf(C,cur,ob,U,t):
        return hnp_scores(traj_xy,pkgs,C,cur,ob,U,synth,G,gzones,t,n)
    r, log = build_route(pkgs,traj_xy,synth,G,gzones,W_cap,True,sf,"HNP-Replan")
    r      = refine(pkgs,traj_xy,r,synth,G,W_cap,gzones)
    m      = evaluate(traj_xy,city,pkgs,r,G,gzones,nzones,synth,W_cap,sess.get("wind_dir",45))
    fp     = build_flight_path(r, traj_xy, traj_gps, city, pkgs)
    return {
        "new_route": r, "metrics": m,
        "log": log[:20], "flight_path": fp,
        "new_gzones": [{"x":z.x,"y":z.y,"r":z.radius,"kind":z.kind,"label":z.label}
                       for z in gzones]
    }

@app.get("/api/locations")
async def get_locations():
    return {
        "locations": [
            {"idx":i,"name":l[0],"lat":l[1],"lon":l[2],"bh":l[3],"cat":l[4]}
            for i,l in enumerate(BLR_LOCATIONS)
        ]
    }

@app.get("/api/compat")
async def compat_graph(density: float = 0.25, seed: int = 42):
    G = build_compat(density, seed)
    edges = [{"src":a,"tgt":b,"ok":ok} for (a,b),ok in G.items() if a < b]
    return {"classes":CLASSES,"edges":edges,"fixed":[list(p) for p in FIXED_INCOMPAT]}

@app.get("/health")
async def health():
    try:
        async with httpx.AsyncClient(timeout=2.0) as cli:
            r = await cli.get(f"{OLLAMA_URL}/api/tags")
            ok = r.status_code == 200
            models = [m["name"] for m in r.json().get("models",[])] if ok else []
    except:
        ok = False; models = []
    return {"status":"ok","ollama":ok,"model":OLLAMA_MODEL,
            "models":models,"sessions":len(SESSIONS)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)
