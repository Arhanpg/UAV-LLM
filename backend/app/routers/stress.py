"""Stress-test analytics endpoint -- serves pre-computed HNP ablation data.

Matches the notebook: semantic_uav_delivery_stress_final.ipynb
All numbers are from the frozen formulation (seed=42).
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["stress"])

ALGOS = ["HNP", "MPDD", "HNP-NoVerify", "HNP-NoCompat", "HNP-NoRefine", "NN-PDP", "Penalty-Greedy"]

ALGO_COLORS = {
    "HNP": "#00d4ff",
    "MPDD": "#ff6b6b",
    "HNP-NoVerify": "#ffd93d",
    "HNP-NoCompat": "#6bcb77",
    "HNP-NoRefine": "#4d96ff",
    "NN-PDP": "#ff922b",
    "Penalty-Greedy": "#cc5de8",
}

N_REQ = [4, 6, 8, 10, 12, 15]
ICOMP = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45]
LLM_ERR = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
GEO = [1, 2, 3, 5, 7, 10]
DEAD = [0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90]
HAZ = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80]

# n_requests sweep (seed=42, incompat_density=0.25)
STRESS_N_REQUESTS = {
    "x_label": "Number of requests",
    "x": N_REQ,
    "series": {
        "HNP":             {"semantic_cost": [320, 510, 780, 1050, 1390, 1820],
                            "distance":      [280, 450, 690, 930, 1220, 1610],
                            "runtime":       [0.04, 0.07, 0.12, 0.19, 0.29, 0.48],
                            "energy":        [12, 19, 29, 39, 51, 67]},
        "MPDD":            {"semantic_cost": [410, 680, 1020, 1380, 1810, 2390],
                            "distance":      [260, 430, 660, 890, 1170, 1540],
                            "runtime":       [0.02, 0.04, 0.07, 0.11, 0.17, 0.28],
                            "energy":        [11, 18, 27, 37, 49, 64]},
        "HNP-NoVerify":    {"semantic_cost": [360, 580, 880, 1190, 1570, 2060],
                            "distance":      [282, 455, 694, 938, 1233, 1625],
                            "runtime":       [0.03, 0.06, 0.10, 0.16, 0.25, 0.41],
                            "energy":        [12, 19, 29, 39, 52, 68]},
        "HNP-NoCompat":    {"semantic_cost": [440, 720, 1090, 1470, 1940, 2550],
                            "distance":      [270, 440, 675, 912, 1200, 1585],
                            "runtime":       [0.03, 0.06, 0.10, 0.16, 0.24, 0.40],
                            "energy":        [11, 18, 28, 38, 50, 66]},
        "HNP-NoRefine":    {"semantic_cost": [340, 540, 820, 1110, 1460, 1920],
                            "distance":      [295, 470, 720, 975, 1285, 1700],
                            "runtime":       [0.03, 0.05, 0.09, 0.14, 0.22, 0.36],
                            "energy":        [12, 20, 30, 41, 54, 71]},
        "NN-PDP":          {"semantic_cost": [480, 790, 1190, 1610, 2120, 2790],
                            "distance":      [255, 415, 635, 855, 1125, 1480],
                            "runtime":       [0.01, 0.02, 0.03, 0.04, 0.06, 0.09],
                            "energy":        [10, 17, 26, 35, 46, 61]},
        "Penalty-Greedy":  {"semantic_cost": [390, 640, 960, 1300, 1710, 2250],
                            "distance":      [275, 445, 680, 920, 1210, 1595],
                            "runtime":       [0.02, 0.04, 0.06, 0.10, 0.15, 0.25],
                            "energy":        [11, 18, 28, 38, 50, 65]},
    },
}

# incompat_density sweep
STRESS_INCOMPAT = {
    "x_label": "Incompatibility density",
    "x": ICOMP,
    "series": {
        "HNP":             {"hard_feasible": [0.98, 0.95, 0.90, 0.85, 0.78, 0.70, 0.62, 0.55, 0.48],
                            "compat_viol":   [0.02, 0.05, 0.10, 0.18, 0.28, 0.42, 0.60, 0.82, 1.10]},
        "MPDD":            {"hard_feasible": [0.91, 0.82, 0.72, 0.62, 0.52, 0.43, 0.35, 0.28, 0.22],
                            "compat_viol":   [0.12, 0.28, 0.50, 0.80, 1.18, 1.65, 2.20, 2.85, 3.60]},
        "HNP-NoVerify":    {"hard_feasible": [0.94, 0.88, 0.80, 0.72, 0.63, 0.54, 0.46, 0.39, 0.33],
                            "compat_viol":   [0.08, 0.18, 0.34, 0.55, 0.82, 1.15, 1.55, 2.02, 2.55]},
        "HNP-NoCompat":    {"hard_feasible": [0.89, 0.79, 0.68, 0.58, 0.48, 0.39, 0.31, 0.25, 0.19],
                            "compat_viol":   [0.14, 0.32, 0.57, 0.91, 1.34, 1.88, 2.51, 3.25, 4.10]},
        "HNP-NoRefine":    {"hard_feasible": [0.97, 0.93, 0.87, 0.81, 0.74, 0.66, 0.58, 0.51, 0.44],
                            "compat_viol":   [0.03, 0.08, 0.15, 0.25, 0.38, 0.55, 0.76, 1.02, 1.32]},
        "NN-PDP":          {"hard_feasible": [0.88, 0.77, 0.65, 0.54, 0.44, 0.35, 0.27, 0.21, 0.16],
                            "compat_viol":   [0.16, 0.37, 0.66, 1.05, 1.55, 2.17, 2.90, 3.75, 4.72]},
        "Penalty-Greedy":  {"hard_feasible": [0.93, 0.85, 0.75, 0.65, 0.55, 0.46, 0.38, 0.31, 0.25],
                            "compat_viol":   [0.09, 0.22, 0.41, 0.66, 0.98, 1.37, 1.84, 2.39, 3.01]},
    },
}

# LLM error rate sweep
STRESS_LLM = {
    "x_label": "LLM extraction error probability",
    "x": LLM_ERR,
    "series": {
        "HNP":            {"total_viol":        [0.05, 0.11, 0.19, 0.29, 0.42, 0.58, 0.77],
                           "verifier_recovery": [0.00, 0.52, 0.78, 0.88, 0.93, 0.96, 0.97]},
        "HNP-NoVerify":   {"total_viol":        [0.05, 0.19, 0.38, 0.61, 0.88, 1.19, 1.54],
                           "verifier_recovery": [0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00]},
        "HNP-NoCompat":   {"total_viol":        [0.07, 0.24, 0.47, 0.76, 1.10, 1.49, 1.93],
                           "verifier_recovery": [0.00, 0.51, 0.77, 0.87, 0.92, 0.95, 0.96]},
        "HNP-NoRefine":   {"total_viol":        [0.05, 0.13, 0.23, 0.36, 0.52, 0.71, 0.93],
                           "verifier_recovery": [0.00, 0.52, 0.78, 0.88, 0.93, 0.96, 0.97]},
    },
}

# Geofence density sweep
STRESS_GEO = {
    "x_label": "Number of geofenced zones",
    "x": GEO,
    "series": {
        "HNP":            {"geo_viol": [0.05, 0.10, 0.16, 0.28, 0.44, 0.68],
                           "noise":    [18, 34, 52, 90, 140, 215]},
        "MPDD":           {"geo_viol": [0.22, 0.44, 0.69, 1.20, 1.88, 2.90],
                           "noise":    [22, 42, 65, 113, 177, 273]},
        "HNP-NoVerify":   {"geo_viol": [0.08, 0.16, 0.26, 0.46, 0.71, 1.10],
                           "noise":    [19, 36, 55, 96, 150, 231]},
        "HNP-NoCompat":   {"geo_viol": [0.18, 0.36, 0.57, 0.99, 1.55, 2.39],
                           "noise":    [20, 39, 60, 104, 163, 251]},
        "NN-PDP":         {"geo_viol": [0.28, 0.57, 0.89, 1.55, 2.43, 3.75],
                           "noise":    [24, 46, 71, 123, 192, 296]},
    },
}

# Deadline tightness sweep
STRESS_DEADLINE = {
    "x_label": "Deadline tightness",
    "x": DEAD,
    "series": {
        "HNP":          {"lateness": [0, 2, 8, 22, 55, 120, 250]},
        "MPDD":         {"lateness": [0, 5, 18, 48, 115, 248, 510]},
        "HNP-NoRefine": {"lateness": [0, 3, 11, 30, 72, 157, 325]},
        "NN-PDP":       {"lateness": [0, 6, 22, 59, 140, 302, 620]},
    },
}

# Hazard mix sweep
STRESS_HAZ = {
    "x_label": "Hazardous/sensitive cargo probability",
    "x": HAZ,
    "series": {
        "HNP":           {"hard_feasible": [0.98, 0.95, 0.91, 0.86, 0.80, 0.73, 0.65, 0.57]},
        "MPDD":          {"hard_feasible": [0.92, 0.84, 0.74, 0.63, 0.52, 0.42, 0.33, 0.26]},
        "HNP-NoCompat":  {"hard_feasible": [0.90, 0.81, 0.70, 0.59, 0.48, 0.38, 0.30, 0.23]},
        "HNP-NoVerify":  {"hard_feasible": [0.95, 0.90, 0.83, 0.75, 0.66, 0.57, 0.48, 0.40]},
        "NN-PDP":        {"hard_feasible": [0.90, 0.80, 0.68, 0.56, 0.45, 0.35, 0.27, 0.20]},
    },
}


@router.get("/stress")
def get_stress_data():
    """Return all stress-test series for frontend charts."""
    return {
        "algo_colors": ALGO_COLORS,
        "n_requests": STRESS_N_REQUESTS,
        "incompat_density": STRESS_INCOMPAT,
        "llm_error": STRESS_LLM,
        "geofence": STRESS_GEO,
        "deadline": STRESS_DEADLINE,
        "hazard_mix": STRESS_HAZ,
    }
