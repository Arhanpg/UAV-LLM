"""Natural-language mission parsing — pre-flight briefs and mid-flight instructions.

Both phases go through the same parser and emit the same structured action list
(PICKUP/DELIVER/REROUTE/ADD_STOP/REMOVE_STOP/SPLIT_DELIVERY/EMERGENCY_RETURN/INFO),
so raw LLM text never reaches the algorithm layer (spec §8.7-8.8). Real LLM by
default, retry once, then a labeled heuristic fallback.
"""

from __future__ import annotations

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


def heuristic_parse(instruction: str, locations: list[str]) -> dict:
    """Keyword-based parse used only when the LLM is unavailable/invalid."""
    text = instruction.lower()
    if any(w in text for w in ("emergency return", "abort", "come back", "return to depot")):
        atype = "EMERGENCY_RETURN"
    elif any(w in text for w in ("split", "ground agent", "hand off", "handoff")):
        atype = "SPLIT_DELIVERY"
    elif any(w in text for w in ("reroute", "avoid", "no-fly", "storm", "thunderstorm")):
        atype = "REROUTE"
    elif any(w in text for w in ("pick up", "pickup", "collect", "grab")):
        atype = "PICKUP"
    elif any(w in text for w in ("deliver", "drop", "bring")):
        atype = "DELIVER"
    elif any(w in text for w in ("add", "also stop", "extra stop")):
        atype = "ADD_STOP"
    elif any(w in text for w in ("remove", "cancel", "skip")):
        atype = "REMOVE_STOP"
    else:
        atype = "INFO"
    kappa = None
    for kw, k in (("insulin", "PHARMA"), ("medicine", "PHARMA"), ("fuel", "FLAMMABLE"),
                  ("oxygen", "OXIDIZER"), ("food", "FOOD"), ("laptop", "ELECTRONICS")):
        if kw in text:
            kappa = k
            break
    return {
        "actions": [
            {
                "type": atype,
                "location": _match_location(instruction, locations),
                "package_kappa": kappa,
                "weight_kg": None,
                "deadline_minutes": None,
                "priority": 2.0 if "urgent" in text or "emergency" in text else 1.0,
                "reason": "keyword heuristic",
            }
        ],
        "constraints_detected": [c for c in ("cold-chain", "deadline", "no-fly") if c.split("-")[0] in text],
        "semantic_cost_impact": "UNKNOWN",
        "summary": f"Heuristic parse: {atype}",
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
            return {**parsed.model_dump(), "source": "llm", "raw": raw}
        except (LLMUnavailable, ValidationError) as e:
            err = str(e)[:200]
    return {**heuristic_parse(instruction, locations), "source": "fallback", "error": err, "raw": None}
