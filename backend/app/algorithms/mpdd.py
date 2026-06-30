"""Phase 1: greedy construction (Eq. 2–7, Paper 1)"""

def node_role(node: int, n: int):
    if 1 <= node <= n: return "P", node - 1
    if n + 1 <= node <= 2 * n: return "D", node - (n + 1)
    return "DEPOT", -1

def compute_delta(j_prime_node, node_role_fn, packages, onboard, K_i_fn):
    """
    Load-aware delta (Eq. 2–3):
    δ(s'ᵢ) = w'ᵢ + Σ_{j' ∈ Kᵢ} δ(j') # Kᵢ = dummy destinations co-located with sᵢ, already picked up
    δ(d'ᵢ) = w'ᵢ
    """
    typ, rid = node_role_fn(j_prime_node, len(packages))
    if rid < 0:
        return 0.0
    req = packages[rid]
    if typ == "D":
        return req.weight
    else: # "P"
        delta = req.weight
        for d_node in K_i_fn(j_prime_node, onboard):
            delta += compute_delta(d_node, node_role_fn, packages, onboard, K_i_fn)
        return delta

def mpdd_fitness_score(traj_coords, current_node, candidates, packages, onboard, K_i_fn, alpha=0.7):
    """
    Fitness (Eq. 4–6):
    d_min = min over feasible candidates j' of dis(i', j')
    w_max = max over feasible candidates j' of δ(j')
    f(i', j') = α · (d_min / dis(i', j')) + (1-α) · (δ(j') / w_max)
    """
    import math

    def dist(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1])
        
    cpos = traj_coords[current_node]
    
    dists = {j: dist(cpos, traj_coords[j]) for j in candidates}
    # d_min only over feasible candidates
    d_min = min([dists[j] for j in candidates if dists[j] > 1e-9], default=1e-6)
    
    deltas = {j: compute_delta(j, node_role, packages, onboard, K_i_fn) for j in candidates}
    w_max = max(deltas.values()) if deltas else 1.0
    if w_max < 1e-9:
        w_max = 1.0

    scores = {}
    zero_dist_candidates = []
    
    for j in candidates:
        if dists[j] < 1e-9:
            zero_dist_candidates.append(j)
            scores[j] = float('inf')  # Handled by tie-breaker
        else:
            scores[j] = alpha * (d_min / dists[j]) + (1 - alpha) * (deltas[j] / w_max)
            
    # Tie-break rule for zero distance
    if zero_dist_candidates:
        # Pick the one with heaviest delta
        best_zero = max(zero_dist_candidates, key=lambda j: deltas[j])
        for j in candidates:
            if j == best_zero:
                scores[j] = float('inf')
            elif dists[j] < 1e-9:
                scores[j] = -float('inf') # Don't pick other zero-dist ones
                
    return scores
