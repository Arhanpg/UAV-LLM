# Math reference — every equation → its implementation

Paper 1 = Chen, Sheu, Bhat, *Planning UAV Trajectory for Multi-Commodity Package
Pickup and Delivery*, IEEE WCNC 2025 (`mpdd.pdf`).
Paper 2 = *Semantic Multi-Commodity UAV Delivery with Implicit Constraint
Discovery* (`UAV_LLM_Project_organized.pdf`).

All file paths are under `backend/app/`.

## Paper 1 — MPDD core

| Ref | Meaning | Where |
|---|---|---|
| Dummy split, length `2m'+2` | one-to-one `(s'ᵢ,d'ᵢ)` pairs, node encoding | `algorithms/mpdd.py` — `node_role`; world build in `geo/locations.py` |
| Eq. 2 | `δ(s'ᵢ) = w'ᵢ + Σ_{j'∈Kᵢ} δ(j')` (co-located ready drops) | `algorithms/mpdd.py` — `compute_delta`, `_colocated_ready_dests` |
| Eq. 3 | `δ(d'ᵢ) = w'ᵢ` | `algorithms/mpdd.py` — `compute_delta` (destination branch) |
| Eq. 4-5 | `d_min`, `w_max` over feasible candidates | `algorithms/mpdd.py` — `mpdd_scores` |
| Eq. 6 | `f = α·(d_min/dis) + (1-α)·(δ/w_max)`, α=0.7 | `algorithms/mpdd.py` — `mpdd_fitness_score` (α = `config.MPDD_ALPHA`) |
| Eq. 7 | `j* = argmax f` greedy selection + depot append | `algorithms/routing.py` — `build_route` |
| Tie-break (dis=0 → pick heaviest δ) | zero-distance candidate dominates | `mpdd_scores` (the `d_min/dis → ∞` term) |
| Algorithm 1 | extend-then-fallback, `i ← max(i+1, j-1)` | `algorithms/tsp_refine.py` — `refine` |
| MST-preorder open TSP (fixed start/end) | Prim MST + preorder, terminal fixed | `algorithms/tsp_refine.py` — `mst_preorder_tsp` |
| Complexity Phase 1 `O(m')`, Phase 2 `O(m'^3)` | empirical growth test | `tests/test_complexity.py` |
| Golden example (Fig. 1) | 5 dummy pairs, location 3 dual role | `tests/test_mpdd_paper_example.py` |

## Paper 2 — semantic / HNP extension

| Ref | Meaning | Where |
|---|---|---|
| Eq. 1 | `Ψ(rᵢ) = ⟨κᵢ, τᵢ, ρᵢ, σᵢ⟩` via LLM structured output | `llm/psi_synthesis.py`, schema `llm/schemas.py` (`PsiSynthesis`) |
| Structured decoding | JSON-schema-constrained `/api/chat` | `llm/ollama_client.py` — `chat_structured` |
| Eq. 7d | `V(Ψ(rⱼ)) = 1` structural verification (Z3) | `verify/smt_verifier.py` — `verify_psi` |
| Eq. 2 | `Gc` incompatibility (hazard / temp / regulatory) | `algorithms/compat_graph.py` — `build_compat`; props in `config.py` (`TEMP_ENVELOPES`, `HAZARD`, `TEMP_SENSITIVE`, `FIXED_INCOMPAT`) |
| Eq. 3-4 | active set `Aᵢ` must induce a clique in `Gc` | `algorithms/compat_graph.py` — `clique_ok`; enforced in `routing.feasible_cands` and `cost.evaluate` |
| Eq. 5-6 | `J(π)` = dist + lateness + noise + energy | `algorithms/cost.py` — `evaluate` (weights `config.ALPHA_OBJ`) |
| Eq. 7a-7b | payload recurrence, `y ≤ W` | `algorithms/cost.py` — `evaluate`; independent re-check `verify/smt_verifier.py` — `verify_route` |
| Eq. 7c | clique feasibility per step (boolean SAT) | `verify/smt_verifier.py` — `verify_route` (edge SAT) |
| Eq. 7e-7f | depot start/end, LTL/SLA deadlines | `cost.evaluate` (deadline lateness), `verify_route` (deadline inequalities) |
| Verifier discrepancy | Z3 vs cost.evaluate on shared hard constraints | `verify/smt_verifier.py` — `discrepancy` |
| Eq. 8a | causality: `π_new[1:t] = π_old[1:t]` | `services/mission_service.py` — `replan_mission`; `algorithms/routing.build_route` mid-mission start |
| Eq. 8b-8c | semantically-valid replan under disruption Δ | `services/mission_service.py` — `replan_mission` (+ `SPLIT_DELIVERY` action in `llm/schemas.py`) |
| Altitude / corridor clearance (§8.4) | tallest building in corridor + margin, ceiling clamp, rate-limited profile | `algorithms/altitude.py` — `corridor_cruise_altitude`, `rate_limited_profile`; index `geo/buildings.py` |

## Six algorithms compared

`algorithms/runner.py` — `run_all_algos`: **MPDD**, **HNP**, **HNP-NoVerify**,
**HNP-NoCompat**, **HNP-NoRefine**, **NN-PDP**. In live mode the HNP synthesis
comes from the real LLM (`mission_service.synthesize_all`); `benchmark` mode uses
the notebook's noise-injection model (`runner.verified_synthesis`).
