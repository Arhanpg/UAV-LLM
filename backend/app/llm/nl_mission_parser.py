"""Natural-language mission parsing — pre-flight briefs and mid-flight instructions.

Both phases go through the same parser and emit the same structured action list
(PICKUP/DELIVER/REROUTE/ADD_STOP/REMOVE_STOP/SPLIT_DELIVERY/EMERGENCY_RETURN/INFO),
so raw LLM text never reaches the algorithm layer (spec §8.7-8.8). Real LLM by
default, retry once, then a labeled heuristic fallback.
"""

from __future__ import annotations
import re

from pydantic import ValidationError

from app.config import CLASSES, LLM_MODE
from app.llm.ollama_client import LLMUnavailable, chat_structured
from app.llm.prompts import NL_INSTRUCTION_V1
from app.llm.schemas import NLParseResult, ollama_format_schema

_SYSTEM = "You output only JSON matching the given schema. Never invent locations that are not in the provided list."


def _match_location(text: str, locations: list[str]) -> str | None:
    tl = text.lower()
    for loc in locations:
        if loc.lower() in tl or any(tok in tl for tok in loc.lower().split()[:2] if len(tok) > 3):
            return loc
    return None


def _extract_via_location(text: str, locations: list[str]) -> str | None:
    """Extract the waypoint location from 'go through X', 'via X', 'stop at X', etc."""
    patterns = [
        r"(?:go through|pass through|route through|via|stop at|visit|through)\s+([\w\s]+?)(?:\s+and|\s+to|\s+then|,|$)",
    ]
    tl = text.lower()
    for pat in patterns:
        m = re.search(pat, tl)
        if m:
            candidate = m.group(1).strip()
            # match against known locations
            for loc in locations:
                if loc.lower() in candidate or candidate in loc.lower():
                    return loc
            # fuzzy: any word match
            words = candidate.split()
            for loc in locations:
                if any(w in loc.lower() for w in words if len(w) > 3):
                    return loc
    return None


def _extract_quantity(text: str) -> int | None:
    """Extract numeric quantity from 'give them 3 notebooks', 'deliver 5 items', etc."""
    m = re.search(r"\b(\d+)\s+(?:notebook|item|package|parcel|unit|box|piece|kg|tablet)", text.lower())
    if m:
        return int(m.group(1))
    return None


def heuristic_parse(instruction: str, locations: list[str]) -> dict:
    """Keyword-based parse used only when the LLM is unavailable/invalid."""
    text = instruction.lower()
    actions = []

    # Check for via/through waypoint patterns FIRST
    via_loc = _extract_via_location(instruction, locations)
    has_via = any(w in text for w in ("go through", "pass through", "route through", "via ", "stop at", "route via"))

    if any(w in text for w in ("emergency return", "abort", "come back", "return to depot")):
        actions.append({
            "type": "EMERGENCY_RETURN",
            "location": None,
            "package_kappa": None,
            "weight_kg": None,
            "deadline_minutes": None,
            "priority": 3.0,
            "reason": "emergency return keyword",
        })
    else:
        # If there's a via/through, emit ADD_STOP first
        if has_via and via_loc:
            actions.append({
                "type": "ADD_STOP",
                "location": via_loc,
                "package_kappa": None,
                "weight_kg": None,
                "deadline_minutes": None,
                "priority": 1.0,
                "reason": "waypoint via instruction",
            })

        # Then the main delivery/pickup action
        if any(w in text for w in ("split", "ground agent", "hand off", "handoff")):
            atype = "SPLIT_DELIVERY"
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
            atype = "INFO" if not has_via else None

        kappa = None
        for kw, k in (("insulin", "PHARMA"), ("medicine", "PHARMA"), ("vaccine", "PHARMA"),
                      ("notebook", "GENERAL"), ("book", "GENERAL"), ("document", "GENERAL"),
                      ("fuel", "FLAMMABLE"), ("oxygen", "OXIDIZER"),
                      ("food", "FOOD"), ("meal", "FOOD"), ("lunch", "FOOD"),
                      ("laptop", "ELECTRONICS"), ("phone", "ELECTRONICS"), ("tablet", "ELECTRONICS")):
            if kw in text:
                kappa = k
                break

        qty = _extract_quantity(instruction)
        delivery_loc = _match_location(instruction, locations)
        # If there's a via, the delivery location should NOT be the same as via_loc
        if has_via and delivery_loc == via_loc:
            # Try to find the actual destination after the via
            remaining = re.sub(r".*?(?:and|to|then)\s+", "", text, count=1)
            delivery_loc = _match_location(remaining, locations) or delivery_loc

        if atype:
            reason_parts = [f"heuristic: {atype}"]
            if qty:
                reason_parts.append(f"qty={qty}")
            actions.append({
                "type": atype,
                "location": delivery_loc,
                "package_kappa": kappa,
                "weight_kg": (qty * 0.3) if qty else None,  # 0.3 kg per item default
                "deadline_minutes": None,
                "priority": 2.0 if "urgent" in text or "emergency" in text else 1.0,
                "reason": ", ".join(reason_parts),
                **(({"quantity": qty}) if qty else {}),
            })

    if not actions:
        actions.append({
            "type": "INFO",
            "location": None,
            "package_kappa": None,
            "weight_kg": None,
            "deadline_minutes": None,
            "priority": 1.0,
            "reason": "no clear intent detected",
        })

    return {
        "actions": actions,
        "constraints_detected": [c for c in ("cold-chain", "deadline", "no-fly") if c.split("-")[0] in text],
        "semantic_cost_impact": "MEDIUM" if len(actions) > 1 else "LOW",
        "summary": f"Heuristic parse: {', '.join(a['type'] for a in actions)}",
        "llm_confidence": 0.3,
    }


async def parse(instruction: str, locations: list[str], phase: str = "midflight") -> dict:
    """Parse an instruction into a validated action plan with a ``source`` field."""
    if LLM_MODE == "benchmark":
        return {**heuristic_parse(instruction, locations), "source": "benchmark", "raw": None}

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
            # Post-process: if LLM missed the via/through waypoint, inject it
            via_loc = _extract_via_location(instruction, locations)
            if via_loc and not any(a.get("type") == "ADD_STOP" and a.get("location") == via_loc
                                   for a in result.get("actions", [])):
                result["actions"].insert(0, {
                    "type": "ADD_STOP",
                    "location": via_loc,
                    "package_kappa": None,
                    "weight_kg": None,
                    "deadline_minutes": None,
                    "priority": 1.0,
                    "reason": "via-waypoint injected by post-processor",
                })
                result["summary"] = f"[+waypoint {via_loc}] " + result.get("summary", "")
            return result
        except (LLMUnavailable, ValidationError) as e:
            err = str(e)[:200]
    return {**heuristic_parse(instruction, locations), "source": "fallback", "error": err, "raw": None}
