"""Natural-language mission parsing -- pre-flight briefs and mid-flight instructions.

Both phases go through the same parser and emit the same structured action list
(PICKUP/DELIVER/REROUTE/ADD_STOP/REMOVE_STOP/SPLIT_DELIVERY/EMERGENCY_RETURN/INFO),
so raw LLM text never reaches the algorithm layer (spec SS8.7-8.8). Real LLM by
default, retry once, then a labeled heuristic fallback.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import ValidationError

from app.config import CLASSES, LLM_MODE
from app.llm.ollama_client import LLMUnavailable, chat_structured
from app.llm.prompts import NL_INSTRUCTION_V1
from app.llm.schemas import NLParseResult, ollama_format_schema

_SYSTEM = "You output only JSON matching the given schema. Never invent locations that are not in the provided list."

VALID_CLASSES = set(CLASSES)
_VIA_TRIGGERS = ("go through", "pass through", "route through", "via ", "stop at", "route via", "visit")

# ---------------------------------------------------------------------------
# Kappa sanitization
# ---------------------------------------------------------------------------
_KAPPA_MAP: dict[str, str] = {
    # general items
    "NOTEBOOK": "GENERAL", "BOOK": "GENERAL", "DOCUMENT": "GENERAL",
    "STATIONERY": "GENERAL", "PARCEL": "GENERAL", "PACKAGE": "GENERAL",
    "LETTER": "GENERAL", "ENVELOPE": "GENERAL", "CLOTHES": "GENERAL",
    # food / dairy
    "MILK": "FOOD", "DAIRY": "FOOD", "LITRE": "FOOD", "LITER": "FOOD",
    "BREAD": "FOOD", "FRUIT": "FOOD", "VEGETABLE": "FOOD", "MEAL": "FOOD",
    "LUNCH": "FOOD", "DINNER": "FOOD", "GROCERY": "FOOD", "NANDINI": "FOOD",
    "KMF": "FOOD", "CURD": "FOOD", "BUTTER": "FOOD", "PANEER": "FOOD",
    "WATER": "FOOD", "JUICE": "FOOD",
    # pharma
    "MEDICINE": "PHARMA", "INSULIN": "PHARMA", "VACCINE": "PHARMA",
    "DRUG": "PHARMA", "TABLET": "PHARMA", "CAPSULE": "PHARMA",
    "INJECTION": "PHARMA", "SYRINGE": "PHARMA", "MEDICAL": "PHARMA",
    # electronics
    "LAPTOP": "ELECTRONICS", "PHONE": "ELECTRONICS", "MOBILE": "ELECTRONICS",
    "CHARGER": "ELECTRONICS", "DEVICE": "ELECTRONICS", "GADGET": "ELECTRONICS",
    "COMPONENT": "ELECTRONICS",
    # hazmat
    "FUEL": "FLAMMABLE", "PETROL": "FLAMMABLE", "DIESEL": "FLAMMABLE",
    "SOLVENT": "FLAMMABLE", "OXYGEN": "OXIDIZER", "PEROXIDE": "OXIDIZER",
    "NITROGEN": "CRYOGENIC", "CRYO": "CRYOGENIC", "LIQUID NITROGEN": "CRYOGENIC",
}


def _sanitize_kappa(raw: object) -> str:
    """Map any LLM or heuristic kappa string to a valid commodity class."""
    if not raw:
        return "GENERAL"
    s = str(raw).strip().upper()
    if s in VALID_CLASSES:
        return s
    for kw, cls in _KAPPA_MAP.items():
        if kw in s:
            return cls
    return "GENERAL"


# ---------------------------------------------------------------------------
# Quantity / unit extraction
# ---------------------------------------------------------------------------
_QTY_PATTERN = re.compile(
    r"""\b(\d+(?:\.\d+)?)   # number
        \s*                   # optional space
        (L|litre|liter|litres|liters|ml|kg|g|units?|pieces?|packets?|bottles?|cartons?|boxes?|items?|notebooks?|packages?|parcels?)?
    """,
    re.IGNORECASE | re.VERBOSE,
)

_UNIT_TO_KG: dict[str, float] = {
    "l": 1.0, "litre": 1.0, "liter": 1.0, "litres": 1.0, "liters": 1.0,
    "ml": 0.001,
    "kg": 1.0, "g": 0.001,
    "unit": 0.3, "units": 0.3,
    "piece": 0.3, "pieces": 0.3,
    "packet": 0.5, "packets": 0.5,
    "bottle": 1.0, "bottles": 1.0,
    "carton": 1.0, "cartons": 1.0,
    "box": 0.5, "boxes": 0.5,
    "item": 0.3, "items": 0.3,
    "notebook": 0.3, "notebooks": 0.3,
    "package": 0.5, "packages": 0.5,
    "parcel": 0.5, "parcels": 0.5,
}


def _extract_quantity(text: str) -> tuple[Optional[int], Optional[float]]:
    """Return (count, weight_kg). E.g. '2 L milk' -> (2, 2.0), '5 items' -> (5, 1.5)."""
    for m in _QTY_PATTERN.finditer(text.lower()):
        num = float(m.group(1))
        unit = (m.group(2) or "").lower().rstrip("s")
        kg = num * _UNIT_TO_KG.get(unit, 0.3)
        return int(num) if num == int(num) else None, round(kg, 3)
    return None, None


# ---------------------------------------------------------------------------
# Location fuzzy matching
# ---------------------------------------------------------------------------
def _match_location(text: str, locations: list[str]) -> Optional[str]:
    """Exact substring match first, then token overlap."""
    tl = text.lower()
    for loc in locations:
        if loc.lower() in tl:
            return loc
    # token overlap: match if 2+ significant words match
    tl_words = set(w for w in tl.split() if len(w) > 3)
    for loc in locations:
        loc_words = set(w for w in loc.lower().split() if len(w) > 3)
        if len(loc_words & tl_words) >= 2:
            return loc
    # single strong token (>=6 chars)
    for loc in locations:
        loc_words = [w for w in loc.lower().split() if len(w) >= 6]
        if any(w in tl for w in loc_words):
            return loc
    return None


def _match_location_full_catalog(text: str) -> Optional[tuple]:
    """Try to match against the FULL location catalog (not just active session)."""
    from app.geo.locations import load_locations
    catalog = load_locations()
    tl = text.lower()
    # Pass 1: exact name substring
    for row in catalog:
        if row[0].lower() in tl or tl in row[0].lower():
            return row
    # Pass 2: abbreviation / alias matching
    aliases: dict[str, str] = {
        "kmf": "KMF Hubli", "nandini": "KMF Hubli", "ksrtc": "KSRTC Bus Stand Dharwad",
        "iit": "IIT Dharwad", "bvb": "BVB College of Engg", "kims": "KIMS Hospital Dharwad",
        "sdm": "SDM Hospital & Medical College", "govt hospital": "Govt District Hospital Dharwad",
        "district hospital": "Govt District Hospital Dharwad", "big bazaar": "Big Bazaar Dharwad",
        "reliance": "Reliance Fresh Dharwad", "town hall": "Dharwad Town Hall Ground",
        "glass house": "Indira Gandhi Glass House Garden",
    }
    for alias, canonical in aliases.items():
        if alias in tl:
            for row in catalog:
                if row[0] == canonical:
                    return row
    # Pass 3: token overlap (2+ words >=4 chars)
    tl_words = set(w for w in tl.split() if len(w) >= 4)
    best_row, best_score = None, 0
    for row in catalog:
        row_words = set(w for w in row[0].lower().split() if len(w) >= 4)
        score = len(row_words & tl_words)
        if score > best_score:
            best_score, best_row = score, row
    if best_score >= 1:
        return best_row
    return None


def _extract_via_location(text: str, locations: list[str]) -> Optional[str]:
    """Extract waypoint from 'go through X', 'via X', 'stop at X'."""
    patterns = [
        r"(?:go through|pass through|route through|via|stop at|visit|through)\s+([\w\s]+?)(?:\s+and|\s+to|\s+then|,|$)",
    ]
    tl = text.lower()
    for pat in patterns:
        m = re.search(pat, tl)
        if m:
            candidate = m.group(1).strip()
            for loc in locations:
                if loc.lower() in candidate or candidate in loc.lower():
                    return loc
            words = [w for w in candidate.split() if len(w) >= 4]
            for loc in locations:
                if any(w in loc.lower() for w in words):
                    return loc
    return None


# ---------------------------------------------------------------------------
# Kappa inference from item description text
# ---------------------------------------------------------------------------
def _infer_kappa_from_text(text: str) -> str:
    t = text.upper()
    for kw, cls in _KAPPA_MAP.items():
        if kw in t:
            return cls
    return "GENERAL"


# ---------------------------------------------------------------------------
# Heuristic parser  (used in benchmark mode and as LLM fallback)
# ---------------------------------------------------------------------------
def heuristic_parse(instruction: str, locations: list[str]) -> dict:
    """Full keyword-based mission parse -- covers all common natural instructions."""
    text = instruction.lower()
    actions: list[dict] = []

    has_via = any(w in text for w in _VIA_TRIGGERS)
    via_loc = _extract_via_location(instruction, locations) if has_via else None

    # --- emergency / abort keywords -----------------------------------------
    if any(w in text for w in ("emergency return", "abort", "come back", "return to depot")):
        actions.append({
            "type": "EMERGENCY_RETURN", "location": None,
            "package_kappa": "GENERAL", "weight_kg": None,
            "deadline_minutes": None, "priority": 3.0,
            "reason": "emergency return keyword",
        })
        return _build_result(actions, text)

    # --- via / ADD_STOP  ----------------------------------------------------
    if has_via and via_loc:
        actions.append({
            "type": "ADD_STOP", "location": via_loc,
            "package_kappa": "GENERAL", "weight_kg": None,
            "deadline_minutes": None, "priority": 1.0,
            "reason": "waypoint via instruction",
        })

    # --- determine primary action type -------------------------------------
    if any(w in text for w in ("split", "ground agent", "hand off", "handoff")):
        atype: Optional[str] = "SPLIT_DELIVERY"
    elif any(w in text for w in ("reroute", "avoid", "no-fly", "storm", "thunderstorm")):
        atype = "REROUTE"
    elif any(w in text for w in ("pick up", "pickup", "collect", "grab", "get", "fetch", "take")):
        atype = "PICKUP"
    elif any(w in text for w in ("deliver", "drop", "bring", "give", "send", "transport", "carry")):
        atype = "DELIVER"
    elif any(w in text for w in ("add stop", "also stop", "extra stop")) and not has_via:
        atype = "ADD_STOP"
    elif any(w in text for w in ("remove", "cancel", "skip")):
        atype = "REMOVE_STOP"
    else:
        atype = None if has_via else "INFO"

    # --- infer kappa from the whole instruction -----------------------------
    kappa = _infer_kappa_from_text(instruction)

    # --- quantity / weight -------------------------------------------------
    qty, weight_kg = _extract_quantity(instruction)

    # --- location matching -------------------------------------------------
    # First try active session locations, then fall back to full catalog
    delivery_loc = _match_location(instruction, locations)
    if delivery_loc is None:
        row = _match_location_full_catalog(instruction)
        if row:
            delivery_loc = row[0]  # canonical name from catalog

    if has_via and delivery_loc == via_loc:
        remaining = re.sub(r".*?(?:and|to|then)\s+", "", text, count=1)
        alt = _match_location(remaining, locations)
        if alt is None:
            row2 = _match_location_full_catalog(remaining)
            if row2:
                alt = row2[0]
        delivery_loc = alt or delivery_loc

    if atype:
        reason_parts = [f"heuristic: {atype}"]
        if qty:
            reason_parts.append(f"qty={qty}")
        if weight_kg:
            reason_parts.append(f"~{weight_kg}kg")
        entry: dict = {
            "type": atype,
            "location": delivery_loc,
            "package_kappa": kappa,
            "weight_kg": weight_kg,
            "deadline_minutes": None,
            "priority": 2.0 if "urgent" in text or "emergency" in text else 1.0,
            "reason": ", ".join(reason_parts),
        }
        if qty:
            entry["quantity"] = qty
        actions.append(entry)

    if not actions:
        actions.append({
            "type": "INFO", "location": None, "package_kappa": "GENERAL",
            "weight_kg": None, "deadline_minutes": None, "priority": 1.0,
            "reason": "no clear intent detected",
        })

    return _build_result(actions, text)


def _build_result(actions: list[dict], text: str) -> dict:
    return {
        "actions": actions,
        "constraints_detected": [
            c for c in ("cold-chain", "deadline", "no-fly") if c.split("-")[0] in text
        ],
        "semantic_cost_impact": "MEDIUM" if len(actions) > 1 else "LOW",
        "summary": f"Heuristic: {', '.join(a['type'] for a in actions)}",
        "llm_confidence": 0.3,
    }


# ---------------------------------------------------------------------------
# Post-processor (runs after BOTH LLM and heuristic paths)
# ---------------------------------------------------------------------------
def _postprocess(result: dict, instruction: str, locations: list[str]) -> dict:
    """Sanitize kappa, inject missed via-waypoints, resolve unknown locations."""
    all_locations = locations[:]
    # Augment with full-catalog names so the LLM output can be resolved
    try:
        from app.geo.locations import load_locations as _ll
        all_locations = [r[0] for r in _ll()]
    except Exception:  # noqa: BLE001
        pass

    for act in result.get("actions", []):
        # Sanitize kappa
        act["package_kappa"] = _sanitize_kappa(act.get("package_kappa"))
        # Resolve location: if LLM gave a string not in active locations,
        # try full-catalog fuzzy match
        loc = act.get("location")
        if loc and loc not in locations:
            row = _match_location_full_catalog(loc)
            if row:
                act["location"] = row[0]

    # Inject missed ADD_STOP for via-triggers
    text = instruction.lower()
    has_via = any(w in text for w in _VIA_TRIGGERS)
    if not has_via:
        return result

    via_loc = _extract_via_location(instruction, all_locations)
    already = any(
        a.get("type") == "ADD_STOP" and a.get("location") == via_loc
        for a in result.get("actions", [])
    )
    if already:
        return result

    waypoint_entry: dict = {
        "type": "ADD_STOP", "location": via_loc,
        "package_kappa": "GENERAL", "weight_kg": None,
        "deadline_minutes": None, "priority": 1.0,
        "reason": "via-waypoint injected by post-processor",
    }
    result["actions"].insert(0, waypoint_entry)
    prefix = f"[+waypoint {via_loc}] " if via_loc else "[+via-stop] "
    result["summary"] = prefix + result.get("summary", "")
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def parse(instruction: str, locations: list[str], phase: str = "midflight") -> dict:
    """Parse an NL instruction. Returns validated action plan with source field."""
    if LLM_MODE == "benchmark":
        result = heuristic_parse(instruction, locations)
        return {**_postprocess(result, instruction, locations), "source": "benchmark", "raw": None}

    schema = ollama_format_schema(NLParseResult)
    user = NL_INSTRUCTION_V1.format(
        phase=phase, locations=locations, classes=CLASSES, instruction=instruction
    )
    err = None
    for attempt in range(2):
        prompt = user if attempt == 0 else f"{user}\n\nPrevious output invalid: {err}\nReturn corrected JSON."
        try:
            data = await chat_structured(_SYSTEM, prompt, schema)
            raw = data.pop("_raw", None)
            parsed = NLParseResult(**data)
            result = {**parsed.model_dump(), "source": "llm", "raw": raw}
            return {**_postprocess(result, instruction, locations), "source": "llm", "raw": raw}
        except (LLMUnavailable, ValidationError) as e:
            err = str(e)[:200]
    result = heuristic_parse(instruction, locations)
    return {**_postprocess(result, instruction, locations), "source": "fallback", "error": err, "raw": None}
