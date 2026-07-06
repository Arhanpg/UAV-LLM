"""Benchmark-mode verified synthesis and full algorithm runner."""

import time
from typing import Dict

import numpy as np

from app.algorithms.cost import evaluate
from app.algorithms.hnp import hnp_scores
from app.algorithms.mpdd import mpdd_scores
from app.algorithms.nn_baseline import nn_scores
from app.algorithms.routing import build_route
from app.algorithms.tsp_refine import refine
from app.config import CLASSES
from app.ws.telemetry import emit


def verified_synthesis(packages, seed, llm_error, Rmax=3):
    rng = np.random.default_rng(seed)
    synth = {}
    vlog = []
    for pkg in packages:
        accepted = None
        recovered = False
        attempts = []
        for _ in range(Rmax):
            p_err = min(0.60, llm_error)
            pred = pkg.kappa if rng.random() > p_err else rng.choice([c for c in CLASSES if c != pkg.kappa]).item()
            v_ok = (rng.random() > 0.01) if pred == pkg.kappa else (rng.random() < 0.02)
            attempts.append({"pred": pred, "verified": bool(v_ok)})
            if v_ok:
                accepted = pred
                break
        if accepted is None:
            accepted = pkg.kappa
            recovered = True
        synth[pkg.idx] = accepted
        vlog.append(
            {
                "req": pkg.idx,
                "true_kappa": pkg.kappa,
                "synth_kappa": accepted,
                "verified": accepted == pkg.kappa,
                "recovered": recovered,
                "attempts": attempts,
            }
        )
    return synth, vlog


def run_all_algos(
    packages, traj_xy, city_nodes, G, gzones, nzones, W_cap, seed,
    wind_dir=270.0, llm_error=0.10, synth_llm=None, verif_log=None,
):
    """Run all six algorithms.

    ``synth_llm``/``verif_log`` come from the real LLM Ψ synthesis in live mode
    (see services.mission_service). When omitted, they are produced by the
    benchmark noise-injection model for reproducing the notebook's plots.
    """
    synth_true = {p.idx: p.kappa for p in packages}
    if synth_llm is None:
        synth_llm, verif_log = verified_synthesis(packages, seed + 1, llm_error)
    verif_log = verif_log or []
    rng = np.random.default_rng(seed + 2)
    synth_noisy = {
        p.idx: (rng.choice([c for c in CLASSES if c != p.kappa]).item() if rng.random() < llm_error else p.kappa)
        for p in packages
    }
    n = len(packages)
    results: Dict[str, dict] = {}

    def _run(label, synth, compat_check, score_type, do_refine):
        if score_type == "hnp":

            def sf(C, cur, ob, U, t):
                return hnp_scores(traj_xy, packages, C, cur, ob, U, synth, G, gzones, t, n)

        elif score_type == "mpdd":

            def sf(C, cur, ob, U, t):
                return mpdd_scores(traj_xy, packages, C, cur, n, ob)

        else:

            def sf(C, cur, ob, U, t):
                return nn_scores(traj_xy, C, cur)

        t0 = time.perf_counter()
        tel = label == "HNP"  # stream telemetry only for the primary run
        r, log = build_route(packages, traj_xy, synth, G, gzones, W_cap, compat_check, sf, label, telemetry=tel)
        if do_refine:
            r = refine(packages, traj_xy, r, synth, G, W_cap, gzones, nzones, city_nodes, telemetry=tel)
        elapsed = time.perf_counter() - t0
        m = evaluate(traj_xy, city_nodes, packages, r, G, gzones, nzones, synth, W_cap, wind_dir)
        m["runtime"] = round(elapsed, 4)
        if tel:
            emit(
                "route_finalized",
                algo=label,
                route=r,
                metrics={k: m[k] for k in ("cost", "dist", "energy", "noise", "lateness", "time_s", "feasible", "viol")},
            )
        return {
            "route": r,
            "log": log,
            "metrics": m,
            "synth": synth,
            "verif_log": verif_log if label == "HNP" else [],
        }

    results["HNP"] = _run("HNP", synth_llm, True, "hnp", True)
    results["MPDD"] = _run("MPDD", synth_true, False, "mpdd", False)
    results["NN-PDP"] = _run("NN-PDP", synth_true, False, "nn", False)
    results["HNP-NoVerify"] = _run("HNP-NoVerify", synth_noisy, True, "hnp", True)
    results["HNP-NoCompat"] = _run("HNP-NoCompat", synth_llm, False, "hnp", True)
    results["HNP-NoRefine"] = _run("HNP-NoRefine", synth_llm, True, "hnp", False)
    return results
