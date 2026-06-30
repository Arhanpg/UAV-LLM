"""Phase 2 trajectory refinement — source-anchored TSP (Paper 1 Algorithm 1)."""
from app.algorithms.routing import node_role
from app.algorithms.cost import evaluate

def mst_preorder_tsp(coords, indices, start, end):
    """
    MST-preorder TSP approximation.
    Builds a minimum spanning tree over the sub-trajectory's locations rooted at the start node,
    then does a preorder traversal. Tour must end at `end` rather than return to `start`.
    """
    if not indices:
        return []
        
    import math
    def dist(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1])
        
    all_nodes = [start] + indices + [end]
    in_mst = {start}
    adj = {node: [] for node in all_nodes}
    
    while len(in_mst) < len(all_nodes):
        best_d, best_u, best_v = float('inf'), -1, -1
        for u in in_mst:
            for v in all_nodes:
                if v not in in_mst:
                    d = dist(coords[u], coords[v])
                    if d < best_d:
                        best_d, best_u, best_v = d, u, v
        if best_u < 0:
            break
        in_mst.add(best_v)
        adj[best_u].append(best_v)
        adj[best_v].append(best_u)
        
    visited_order = []
    stack = [(start, -1)]
    visited_set = set()
    while stack:
        node, parent = stack.pop()
        if node in visited_set:
            continue
        visited_set.add(node)
        visited_order.append(node)
        
        children = sorted([nb for nb in adj[node] if nb != parent],
                           key=lambda x: dist(coords[node], coords[x]))
        for child in reversed(children): 
            stack.append((child, node))
            
    middle = [v for v in visited_order if v not in {start, end}]
    return middle

def refine(packages, traj_xy, route, synth, G, W, gzones):
    """
    Paper 1 Algorithm 1: Exact control flow
    """
    n = len(packages)
    
    def pick_pos(rt):
        # returns indices of route that are source (pickup) nodes
        return [idx for idx, nd in enumerate(rt) if node_role(nd, n)[0] == "P"]

    best = route[:]
    anchors = [0] + pick_pos(best) + [len(best) - 1]
    m_prime = len(anchors) - 2 
    
    i = 1
    while i < m_prime + 1:
        if anchors[i+1] - anchors[i] > 2:
            extended = False
            for j in range(i + 1, m_prime + 2):
                lo, hi = anchors[i], anchors[j]
                
                segment_nodes = best[lo:hi+1]
                start_node = segment_nodes[0]
                end_node = segment_nodes[-1]
                middle_nodes = segment_nodes[1:-1]
                
                new_middle = mst_preorder_tsp(traj_xy, middle_nodes, start_node, end_node)
                cand = best[:lo] + [start_node] + new_middle + [end_node] + best[hi+1:]
                
                # Check feasible and strictly shorter
                base_m = evaluate(traj_xy, [], packages, best, G, [], [], synth, W)
                cand_m = evaluate(traj_xy, [], packages, cand, G, [], [], synth, W)
                
                if (cand_m["dist"] < base_m["dist"] - 1e-9 and 
                    cand_m["pv"] == 0 and cand_m["rv"] == 0 and cand_m["cv"] == 0):
                    best = cand
                    anchors = [0] + pick_pos(best) + [len(best) - 1]
                    extended = True
                else:
                    i = max(i + 1, j - 1)
                    break
            else:
                if not extended:
                    i = i + 1
        else:
            i = i + 1
            
    return best
