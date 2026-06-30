"""Commodity compatibility graph Gc (Paper 2 Eq. 2, 4)."""

import itertools
from typing import Dict, Tuple

import numpy as np

from app.config import CLASSES, FIXED_INCOMPAT


def build_compat(density: float, seed: int) -> Dict[Tuple[str, str], bool]:
    rng = np.random.default_rng(seed)
    G = {(a, b): True for a in CLASSES for b in CLASSES}
    for a, b in FIXED_INCOMPAT:
        G[(a, b)] = G[(b, a)] = False
    pairs = [(a, b) for i, a in enumerate(CLASSES) for b in CLASSES[i + 1 :]]
    for a, b in pairs:
        if G[(a, b)] and rng.random() < density:
            G[(a, b)] = G[(b, a)] = False
    return G


def clique_ok(classes: list, G: dict) -> bool:
    return all(G.get((a, b), True) for a, b in itertools.combinations(classes, 2))


def is_compatible_classset(classes: list, G: dict) -> bool:
    return clique_ok(classes, G)
