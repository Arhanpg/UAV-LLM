"""FastAPI application entry point."""

import math
import time

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.algorithms.compat_graph import build_compat
from app.algorithms.cost import evaluate
from app.algorithms.hnp import hnp_scores
from app.algorithms.runner import run_all_algos
from app.algorithms.routing import build_route
from app.algorithms.tsp_refine import refine
from app.config import CLASSES, OLLAMA_BASE_URL, OLLAMA_MODEL
from app.geo.locations import generate_world, load_locations
from app.llm.nl_mission_parser import parse as nl_parse
from app.models.mission import GeoZone
from app.models.session import GenConfig, NLReq, ReplanReq, SessionStore
from app.services.flight_path import build_flight_path

app = FastAPI(title="UAV-LLM Dharwad Real-World System", version="5.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SESSIONS = SessionStore()

from pathlib import Path

ROOT_INDEX = Path(__file__).resolve().parents[2] / "index.html"


@app.get("/")
async def root():
    if ROOT_INDEX.exists():
        return FileResponse(str(ROOT_INDEX))
    return {"message": "UAV-LLM API — use frontend at :5173"}


@app.post("/api/generate")
async def generate(cfg: GenConfig):
    city, pkgs, G, gzones, nzones, W_cap, traj_xy, traj_gps = generate_world(
        cfg.loc_indices,
        cfg.pkg_requests,
        cfg.seed,
        cfg.incompat_density,
        cfg.n_gfz,
        cfg.deadline_tight,
        cfg.hazard_mix,
        cfg.cap_ratio,
        build_compat,
    )
    results = run_all_algos(pkgs, traj_xy, city, G, gzones, nzones, W_cap, cfg.seed, cfg.wind_dir, cfg.llm_error)
    sid = f"s{cfg.seed}_{int(time.time() * 1000) % 100000}"
    SESSIONS.set(
        sid,
        {
            "city": city,
            "pkgs": pkgs,
            "G": G,
            "gzones": gzones,
            "nzones": nzones,
            "W_cap": W_cap,
            "traj_xy": traj_xy,
            "traj_gps": traj_gps,
            "results": results,
            "wind_dir": cfg.wind_dir,
        },
    )
    hnp_route = results["HNP"]["route"]
    flight_path = build_flight_path(hnp_route, traj_xy, traj_gps, city, pkgs)
    incompat_pairs = [[a, b] for (a, b), ok in G.items() if not ok and a < b]
    catalog = load_locations()
    return {
        "session_id": sid,
        "origin": {"lat": city[0].lat, "lon": city[0].lon, "label": city[0].label},
        "city": [
            {
                "idx": n.idx,
                "lat": n.lat,
                "lon": n.lon,
                "x": round(n.x, 1),
                "y": round(n.y, 1),
                "bh": n.building_height,
                "label": n.label,
                "category": n.category,
                "description": n.description,
                "depot": n.is_depot,
                "pickups": n.pickups,
                "drops": n.drops,
            }
            for n in city
        ],
        "packages": [
            {
                "idx": p.idx,
                "pickup": p.pickup_loc,
                "delivery": p.delivery_loc,
                "weight": round(p.weight, 2),
                "kappa": p.kappa,
                "deadline": round(p.deadline, 1),
                "priority": p.priority,
                "temp": p.temp_required,
                "desc": p.description,
            }
            for p in pkgs
        ],
        "gzones": [
            {"lat": z.lat, "lon": z.lon, "x": z.x, "y": z.y, "r": z.radius, "kind": z.kind, "label": z.label}
            for z in gzones
        ],
        "nzones": [
            {"lat": z.lat, "lon": z.lon, "x": z.x, "y": z.y, "r": z.radius, "kind": z.kind, "label": z.label}
            for z in nzones
        ],
        "W_cap": round(W_cap, 2),
        "traj_xy": traj_xy,
        "traj_gps": traj_gps,
        "results": {
            k: {
                "route": v["route"],
                "metrics": v["metrics"],
                "log": v["log"][:40],
                "verif_log": v.get("verif_log", [])[:20],
            }
            for k, v in results.items()
        },
        "flight_path": flight_path,
        "incompat_pairs": incompat_pairs,
        "classes": CLASSES,
        "all_locations": [
            {
                "idx": i,
                "name": l[0],
                "lat": l[1],
                "lon": l[2],
                "bh": l[3],
                "cat": l[4],
                "desc": l[5] if len(l) > 5 else "",
            }
            for i, l in enumerate(catalog)
        ],
    }


@app.post("/api/llm/instruction")
async def nl_instruction(req: NLReq):
    sess = SESSIONS.get(req.session_id) or {}
    city = sess.get("city", [])
    city_labels = [c.label for c in city] if city else []
    phase = "preflight" if req.phase in ("initial", "preflight") else "midflight"
    result = await nl_parse(req.instruction, city_labels, phase)
    return {"instruction": req.instruction, "phase": phase, "result": result, "ollama_model": OLLAMA_MODEL}


@app.post("/api/replan")
async def replan(req: ReplanReq):
    sess = SESSIONS.get(req.session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    d = req.disruption
    if d.get("type") == "nofly":
        gx = float(d.get("x", 0))
        gy = float(d.get("y", 0))
        origin_lat = sess["city"][0].lat
        origin_lon = sess["city"][0].lon
        gz_lat = origin_lat + (gy / 111111)
        gz_lon = origin_lon + (gx / (111111 * math.cos(math.radians(origin_lat))))
        sess["gzones"].append(
            GeoZone(lat=gz_lat, lon=gz_lon, x=gx, y=gy, radius=float(d.get("r", 150)), kind="nofly", label="Emergency No-Fly")
        )
    pkgs = sess["pkgs"]
    traj_xy = sess["traj_xy"]
    G = sess["G"]
    gzones = sess["gzones"]
    nzones = sess["nzones"]
    W_cap = sess["W_cap"]
    city = sess["city"]
    traj_gps = sess["traj_gps"]
    synth = {p.idx: p.kappa for p in pkgs}
    n = len(pkgs)

    def sf(C, cur, ob, U, t):
        return hnp_scores(traj_xy, pkgs, C, cur, ob, U, synth, G, gzones, t, n)

    r, log = build_route(pkgs, traj_xy, synth, G, gzones, W_cap, True, sf, "HNP-Replan")
    r = refine(pkgs, traj_xy, r, synth, G, W_cap, gzones)
    m = evaluate(traj_xy, city, pkgs, r, G, gzones, nzones, synth, W_cap, sess.get("wind_dir", 270))
    fp = build_flight_path(r, traj_xy, traj_gps, city, pkgs)
    return {
        "new_route": r,
        "metrics": m,
        "log": log[:20],
        "flight_path": fp,
        "new_gzones": [
            {"lat": z.lat, "lon": z.lon, "x": z.x, "y": z.y, "r": z.radius, "kind": z.kind, "label": z.label}
            for z in gzones
        ],
    }


@app.get("/api/locations")
async def get_locations():
    catalog = load_locations()
    return {
        "locations": [
            {
                "idx": i,
                "name": l[0],
                "lat": l[1],
                "lon": l[2],
                "bh": l[3],
                "cat": l[4],
                "desc": l[5] if len(l) > 5 else "",
            }
            for i, l in enumerate(catalog)
        ]
    }


@app.get("/health")
async def health():
    try:
        async with httpx.AsyncClient(timeout=2.0) as cli:
            r = await cli.get(f"{OLLAMA_BASE_URL}/api/tags")
            ok = r.status_code == 200
            models = [m["name"] for m in r.json().get("models", [])] if ok else []
    except Exception:
        ok = False
        models = []
    return {
        "status": "ok",
        "ollama": ok,
        "model": OLLAMA_MODEL,
        "models": models,
        "sessions": len(SESSIONS),
        "city": "Dharwad-Hubli, Karnataka",
    }
