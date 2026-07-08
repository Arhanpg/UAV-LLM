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


def _match_location(text: str, locations: list[str]) -> Optional[str]:
    tl = text.lower()
    for loc in locations:
        if loc.lower() in tl:
            return loc
        words = [w for w in loc.lower().split() if len(w) > 3]
        if words and any(w in tl for w in words[:2]):
            return loc
    return None


def _extract_via_location(text: str, locations: list[str]) -> Optional[str]:
    """Extract the waypoint location from 'go through X', 'via X', 'stop at X', etc."""
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
            words = [w for w in candidate.split() if len(w) > 3]
            for loc in locations:
                if any(w in loc.lower() for w in words):
                    return loc
    return None


def _extract_quantity(text: str) -> Optional[int]:
    """Extract numeric quantity: 'give them 3 notebooks', 'deliver 5 items'."""
    m = re.search(r"\b(\d+)\s+(?:notebook|item|package|parcel|unit|box|piece|kg|tablet)", text.lower())
    return int(m.group(1)) if m else None


def _sanitize_kappa(raw: object) -> str:
    """Map any LLM kappa string to a valid commodity class, defaulting to GENERAL."""
    if not raw:
        return "GENERAL"
    s = str(raw).strip().upper()
    if s in VALID_CLASSES:
        return s
    # common heuristic mappings
    mapping = {
        "NOTEBOOK": "GENERAL", "BOOK": "GENERAL", "DOCUMENT": "GENERAL",
        "STATIONERY": "GENERAL", "MEDICINE": "PHARMA", "INSULIN": "PHARMA",
        "VACCINE": "PHARMA", "FUEL": "FLAMMABLE", "LAPTOP": "ELECTRONICS",
        "PHONE": "ELECTRONICS", "TABLET": "ELECTRONICS",
    }
    for kw, cls in mapping.items():
        if kw in s:
            return cls
    return "GENERAL"


def heuristic_parse(instruction: str, locations: list[str]) -> dict:
    """Keyword-based parse used only when the LLM is unavailable/invalid."""
    text = instruction.lower()
    actions = []

    has_via = any(w in text for w in _VIA_TRIGGERS)
    via_loc = _extract_via_location(instruction, locations) if has_via else None

    if any(w in text for w in ("emergency return", "abort", "come back", "return to depot")):
        actions.append({
            "type": "EMERGENCY_RETURN",
            "location": None,
            "package_kappa": "GENERAL",
            "weight_kg": None,
            "deadline_minutes": None,
            "priority": 3.0,
            "reason": "emergency return keyword",
        })
    else:
        if has_via and via_loc:
            actions.append({
                "type": "ADD_STOP",
                "location": via_loc,
                "package_kappa": "GENERAL",
                "weight_kg": None,
                "deadline_minutes": None,
                "priority": 1.0,
                "reason": "waypoint via instruction",
            })

        if any(w in text for w in ("split", "ground agent", "hand off", "handoff")):
            atype: Optional[str] = "SPLIT_DELIVERY"
        elif any(w in text for w in ("reroute", "avoid", "no-fly", "storm", "thunderstorm")):
            atype = "REROUTE"
        elif any(w in text for w in ("pick up", "pickup", "collect", "grab")):
            atype = "PICKUP"
        elif any(w in text for w in ("deliver", "drop", "bring", "give", "send")):
            atype = "DELIVER"
        elif any(w in text for w in ("add", "also stop", "extra stop")) and not has_via:
            atype = "ADD_STOP"
        elif any(w in text for w in ("remove", "cancel", "skip")):
            atype = "REMOVE_STOP"
        else:
            atype = None if has_via else "INFO"

        kappa = "GENERAL"
        for kw, k in (
            ("insulin", "PHARMA"), ("medicine", "PHARMA"), ("vaccine", "PHARMA"),
            ("notebook", "GENERAL"), ("book", "GENERAL"), ("document", "GENERAL"),
            ("fuel", "FLAMMABLE"), ("oxygen", "OXIDIZER"),
            ("food", "FOOD"), ("meal", "FOOD"), ("lunch", "FOOD"),
            ("laptop", "ELECTRONICS"), ("phone", "ELECTRONICS"), ("tablet", "ELECTRONICS"),
        ):
            if kw in text:
                kappa = k
                break

        qty = _extract_quantity(instruction)
        delivery_loc = _match_location(instruction, locations)
        if has_via and delivery_loc == via_loc:
            remaining = re.sub(r".*?(?:and|to|then)\s+", "", text, count=1)
            delivery_loc = _match_location(remaining, locations) or delivery_loc

        if atype:
            reason_parts = [f"heuristic: {atype}"]
            if qty:
                reason_parts.append(f"qty={qty}")
            base: dict = {
                "type": atype,
                "location": delivery_loc,
                "package_kappa": kappa,
                "weight_kg": (qty * 0.3) if qty else None,
                "deadline_minutes": None,
                "priority": 2.0 if "urgent" in text or "emergency" in text else 1.0,
                "reason": ", ".join(reason_parts),
            }
            if qty:
                base["quantity"] = qty
            actions.append(base)

    if not actions:
        actions.append({
            "type": "INFO",
            "location": None,
            "package_kappa": "GENERAL",
            "weight_kg": None,
            "deadline_minutes": None,
            "priority": 1.0,
            "reason": "no clear intent detected",
        })

    return {
        "actions": actions,
        "constraints_detected": [c for c in ("cold-chain", "deadline", "no-fly") if c.split("-")[0] in text],
        "semantic_cost_impact": "MEDIUM" if len(actions) > 1 else "LOW",
        "summary": f"Heuristic: {', '.join(a['type'] for a in actions)}",
        "llm_confidence": 0.3,
    }


def _postprocess(result: dict, instruction: str, locations: list[str]) -> dict:
    """Sanitize LLM output: fix kappa values and inject missed via-waypoints."""
    for act in result.get("actions", []):
        act["package_kappa"] = _sanitize_kappa(act.get("package_kappa"))

    # If instruction contains a via-trigger but no ADD_STOP was emitted, inject one.
    text = instruction.lower()
    has_via = any(w in text for w in _VIA_TRIGGERS)
    if not has_via:
        return result

    via_loc = _extract_via_location(instruction, locations)
    already_has = any(
        a.get("type") == "ADD_STOP" and a.get("location") == via_loc
        for a in result.get("actions", [])
    )
    if already_has:
        return result

    waypoint_entry: dict = {
        "type": "ADD_STOP",
        "location": via_loc,
        "package_kappa": "GENERAL",
        "weight_kg": None,
        "deadline_minutes": None,
        "priority": 1.0,
        "reason": "via-waypoint injected by post-processor",
    }
    result["actions"].insert(0, waypoint_entry)
    prefix = f"[+waypoint {via_loc}] " if via_loc else "[+via-stop] "
    result["summary"] = prefix + result.get("summary", "")
    return result


async def parse(instruction: str, locations: list[str], phase: str = "midflight") -> dict:
    """Parse an instruction into a validated action plan with a ``source`` field."""
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
