"""Mission orchestration: LLM Ψ synthesis → verify → run algorithms → 3D path.

This is the single place where a mission is generated or replanned. In live mode
(default) it calls the real local LLM for every package's Ψ synthesis, verifies
each with Z3, runs all six algorithms, builds the rate-limited 3D flight path,
runs an independent Z3 route re-check, streams telemetry, and persists the
mission to SQLite. Benchmark mode swaps Ψ for the notebook's noise model.
"""

from __future__ import annotations

import math
import time

from app.algorithms.compat_graph import build_compat
from app.algorithms.cost import evaluate
from app.algorithms.hnp import hnp_scores
from app.algorithms.routing import build_route, node_role
from app.algorithms.runner import run_all_algos
from app.algorithms.tsp_refine import refine
from app.config import CLASSES, LLM_MODE, OLLAMA_MODEL
from app.geo.locations import generate_world, load_locations
from app.llm.psi_synthesis import synthesize
from app.models.db import get_mission, save_mission
from app.models.mission import GeoZone
from app.models.session import SessionStore
from app.services.flight_path import altitude_profile, build_flight_path
from app.verify.smt_verifier import discrepancy, verify_psi, verify_route
from app.ws.telemetry import emit, session_context

SESSIONS = SessionStore()


def _known_zone_names(gzones) -> list[str]:
    return ["residential", "no-fly", "noise", "airport", "hospital"] + [z.label for z in gzones]


async def synthesize_all(packages, gzones):
    """Run real LLM Ψ synthesis + Z3 structural verification for every package."""
    known = _known_zone_names(gzones)
    synth: dict[int, str] = {}
    verif_log: list[dict] = []
    for pkg in packages:
        emit("llm_prompt_sent", req=pkg.idx, text=pkg.description or f"{pkg.kappa} package")
        psi = await synthesize(pkg.description or f"{pkg.kappa} package")
        raw = psi.get("raw") or {}
        emit("llm_response_received", req=pkg.idx, source=psi.get("source"), response=raw.get("response"))
        v = verify_psi(psi, known_zones=known)
        emit(
            "psi_synthesis_result",
            req=pkg.idx, kappa=psi["kappa"], temp=[psi["temp_min"], psi["temp_max"]],
            deadline=psi.get("deadline_minutes"), priority=psi.get("priority"), source=psi["source"],
        )
        emit("smt_verify_result", scope="psi", req=pkg.idx, ok=v["ok"], reasons=v["reasons"], checks=v["checks"])
        accepted = psi["kappa"] if v["ok"] else pkg.kappa  # recover to declared class if Ψ is structurally invalid
        synth[pkg.idx] = accepted
        verif_log.append(
            {
                "req": pkg.idx,
                "true_kappa": pkg.kappa,
                "synth_kappa": psi["kappa"],
                "accepted": accepted,
                "verified": v["ok"],
                "recovered": not v["ok"],
                "source": psi["source"],
                "reasons": v["reasons"],
                "psi": {k: psi.get(k) for k in
                        ("kappa", "temp_min", "temp_max", "deadline_minutes", "priority", "prohibited_zones", "confidence")},
                "prompt": raw.get("prompt"),
                "response": raw.get("response"),
            }
        )
    return synth, verif_log


def _serialize(city, pkgs, gzones, nzones, G, W_cap, traj_xy, traj_gps, results, flight_path, alt_profile, verifier, mode):
    incompat_pairs = [[a, b] for (a, b), ok in G.items() if not ok and a < b]
    catalog = load_locations()
    return {
        "origin": {"lat": city[0].lat, "lon": city[0].lon, "label": city[0].label},
        "llm_mode": mode,
        "model": OLLAMA_MODEL,
        "city": [
            {"idx": n.idx, "lat": n.lat, "lon": n.lon, "x": round(n.x, 1), "y": round(n.y, 1), "bh": n.building_height,
             "label": n.label, "category": n.category, "description": n.description, "depot": n.is_depot,
             "pickups": n.pickups, "drops": n.drops}
            for n in city
        ],
        "packages": [
            {"idx": p.idx, "pickup": p.pickup_loc, "delivery": p.delivery_loc, "weight": round(p.weight, 2),
             "kappa": p.kappa, "deadline": round(p.deadline, 1), "priority": p.priority, "temp": p.temp_required,
             "desc": p.description}
            for p in pkgs
        ],
        "gzones": [{"lat": z.lat, "lon": z.lon, "x": z.x, "y": z.y, "r": z.radius, "kind": z.kind, "label": z.label} for z in gzones],
        "nzones": [{"lat": z.lat, "lon": z.lon, "x": z.x, "y": z.y, "r": z.radius, "kind": z.kind, "label": z.label} for z in nzones],
        "W_cap": round(W_cap, 2),
        "traj_xy": traj_xy,
        "traj_gps": traj_gps,
        "results": {
            k: {"route": v["route"], "metrics": v["metrics"], "log": v["log"][:60], "verif_log": v.get("verif_log", [])[:40]}
            for k, v in results.items()
        },
        "flight_path": flight_path,
        "alt_profile": alt_profile,
        "verifier": verifier,
        "incompat_pairs": incompat_pairs,
        "classes": CLASSES,
        "all_locations": [
            {"idx": i, "name": loc[0], "lat": loc[1], "lon": loc[2], "bh": loc[3], "cat": loc[4],
             "desc": loc[5] if len(loc) > 5 else ""}
            for i, loc in enumerate(catalog)
        ],
    }


async def generate_mission(cfg) -> dict:
    city, pkgs, G, gzones, nzones, W_cap, traj_xy, traj_gps = generate_world(
        cfg.loc_indices, cfg.pkg_requests, cfg.seed, cfg.incompat_density, cfg.n_gfz,
        cfg.deadline_tight, cfg.hazard_mix, cfg.cap_ratio, build_compat,
    )
    sid = f"s{cfg.seed}_{int(time.time() * 1000) % 100000}"
    mode = "benchmark" if LLM_MODE == "benchmark" else "live"

    with session_context(sid):
        if mode == "live":
            synth_llm, verif_log = await synthesize_all(pkgs, gzones)
        else:
            synth_llm, verif_log = None, None
        results = run_all_algos(
            pkgs, traj_xy, city, G, gzones, nzones, W_cap, cfg.seed, cfg.wind_dir, cfg.llm_error, synth_llm, verif_log
        )
        hnp = results["HNP"]
        vroute = verify_route(hnp["route"], pkgs, hnp["synth"], G, W_cap, traj_xy)
        disc = discrepancy(vroute, hnp["metrics"])
        emit("smt_verify_result", scope="route", ok=vroute["ok"], reasons=vroute["reasons"], discrepancy=disc)
        flight_path = build_flight_path(hnp["route"], traj_xy, traj_gps, city, pkgs)
        alt_prof, _cruise = altitude_profile(hnp["route"], traj_xy, city)

    verifier = {"route": vroute, "discrepancy": disc}
    SESSIONS.set(sid, {
        "city": city, "pkgs": pkgs, "G": G, "gzones": gzones, "nzones": nzones, "W_cap": W_cap,
        "traj_xy": traj_xy, "traj_gps": traj_gps, "results": results, "wind_dir": cfg.wind_dir,
        "synth_llm": hnp["synth"], "config": cfg.model_dump(),
    })
    payload = {"session_id": sid, **_serialize(city, pkgs, gzones, nzones, G, W_cap, traj_xy, traj_gps, results, flight_path, alt_prof, verifier, mode)}
    save_mission(sid, cfg.model_dump(), {
        "hnp_dist": hnp["metrics"]["dist"], "hnp_cost": hnp["metrics"]["cost"],
        "feasible": hnp["metrics"]["feasible"], "n_packages": len(pkgs), "mode": mode,
        "verifier_ok": vroute["ok"], "discrepancy": bool(disc),
    })
    return payload


def _rehydrate(sid: str):
    """Reconstruct a full session from its persisted config (deterministic)."""
    rec = get_mission(sid)
    if not rec:
        return None
    from app.models.session import GenConfig

    cfg = GenConfig(**rec["config"])
    city, pkgs, G, gzones, nzones, W_cap, traj_xy, traj_gps = generate_world(
        cfg.loc_indices, cfg.pkg_requests, cfg.seed, cfg.incompat_density, cfg.n_gfz,
        cfg.deadline_tight, cfg.hazard_mix, cfg.cap_ratio, build_compat,
    )
    synth = {p.idx: p.kappa for p in pkgs}
    results = run_all_algos(pkgs, traj_xy, city, G, gzones, nzones, W_cap, cfg.seed, cfg.wind_dir, cfg.llm_error)
    sess = {"city": city, "pkgs": pkgs, "G": G, "gzones": gzones, "nzones": nzones, "W_cap": W_cap,
            "traj_xy": traj_xy, "traj_gps": traj_gps, "results": results, "wind_dir": cfg.wind_dir,
            "synth_llm": results["HNP"]["synth"], "config": rec["config"]}
    SESSIONS.set(sid, sess)
    return sess


def replan_mission(sid: str, disruption: dict, flown_steps: int = 0, summary: str = "") -> dict:
    """Causality-preserving dynamic replan (Paper 2 Eq. 8a-8c)."""
    sess = SESSIONS.get(sid) or _rehydrate(sid)
    if not sess:
        raise KeyError("session not found")

    pkgs, traj_xy, G, gzones, nzones = sess["pkgs"], sess["traj_xy"], sess["G"], sess["gzones"], sess["nzones"]
    W_cap, city, traj_gps = sess["W_cap"], sess["city"], sess["traj_gps"]
    synth = sess.get("synth_llm") or {p.idx: p.kappa for p in pkgs}
    n = len(pkgs)

    with session_context(sid):
        emit("disruption_detected", disruption=disruption, summary=summary)
        # Inject the new no-fly / weather zone.
        if disruption.get("type") in ("nofly", "weather", "storm"):
            gx, gy = float(disruption.get("x", 0)), float(disruption.get("y", 0))
            olat, olon = city[0].lat, city[0].lon
            gzones.append(GeoZone(
                lat=olat + gy / 111111, lon=olon + gx / (111111 * math.cos(math.radians(olat))),
                x=gx, y=gy, radius=float(disruption.get("r", 180)), kind="nofly",
                label=summary or "Emergency No-Fly",
            ))

        old_route = sess["results"]["HNP"]["route"]
        t = max(0, min(int(flown_steps), len(old_route) - 1))
        prefix = old_route[:t]
        current = prefix[-1] if prefix else 0
        prefix_nodes = set(prefix)
        remaining = set(range(1, 2 * n + 1)) - prefix_nodes
        onboard = {rid for rid in range(n)
                   if (rid + 1) in prefix_nodes and (rid + n + 1) not in prefix_nodes}
        y0 = sum(pkgs[rid].weight for rid in onboard)

        emit("replan_start", flown_steps=t, current_node=current, onboard=len(onboard), remaining=len(remaining))

        def sf(C, cur, ob, U, tt):
            return hnp_scores(traj_xy, pkgs, C, cur, ob, U, synth, G, gzones, tt, n)

        suffix, log = build_route(
            pkgs, traj_xy, synth, G, gzones, W_cap, True, sf, "HNP-Replan", telemetry=True,
            start_node=current, init_U=remaining, init_onboard=onboard, init_y=y0,
        )
        suffix = refine(pkgs, traj_xy, suffix, synth, G, W_cap, gzones, nzones, city, telemetry=True)
        new_route = (prefix[:-1] + suffix) if prefix else suffix

        m = evaluate(traj_xy, city, pkgs, new_route, G, gzones, nzones, synth, W_cap, sess.get("wind_dir", 270))
        vroute = verify_route(new_route, pkgs, synth, G, W_cap, traj_xy)
        emit("replan_complete", route_len=len(new_route), dist=m["dist"], feasible=m["feasible"], verifier_ok=vroute["ok"])

        fp = build_flight_path(new_route, traj_xy, traj_gps, city, pkgs)
        alt_prof, _ = altitude_profile(new_route, traj_xy, city)

    sess["results"]["HNP"]["route"] = new_route  # so a further replan builds on this
    return {
        "session_id": sid,
        "new_route": new_route,
        "flown_prefix_len": t,
        "metrics": m,
        "verifier": {"route": vroute},
        "log": log[:30],
        "flight_path": fp,
        "alt_profile": alt_prof,
        "new_gzones": [{"lat": z.lat, "lon": z.lon, "x": z.x, "y": z.y, "r": z.radius, "kind": z.kind, "label": z.label} for z in gzones],
    }
