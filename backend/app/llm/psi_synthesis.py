"""Ψ constraint synthesis — Paper 2 Eq. 1.

Maps a natural-language delivery request to ⟨κ, τ, ρ, σ⟩ using the local LLM by
default (LLM_MODE="live"). Validates against the PsiSynthesis schema, retries
once with the validation error fed back, then falls back to a clearly-labeled
rule-based heuristic (spec §8.3 — never silently pretend a heuristic was the LLM).
"""

from __future__ import annotations

from pydantic import ValidationError

from app.config import CLASSES, LLM_MODE, TEMP_ENVELOPES
from app.llm.ollama_client import LLMUnavailable, chat_structured
from app.llm.prompts import PSI_SYNTHESIS_V1
from app.llm.schemas import PsiSynthesis, ollama_format_schema

_SYSTEM = "You output only JSON matching the given schema. Be precise and conservative about safety constraints."

_KEYWORDS = [
    ("insulin", "PHARMA"), ("vaccine", "PHARMA"), ("medicine", "PHARMA"), ("pharma", "PHARMA"),
    ("blood", "PHARMA"), ("cryo", "CRYOGENIC"), ("frozen", "CRYOGENIC"), ("liquid nitrogen", "CRYOGENIC"),
    ("fuel", "FLAMMABLE"), ("solvent", "FLAMMABLE"), ("petrol", "FLAMMABLE"), ("gas canister", "FLAMMABLE"),
    ("oxygen", "OXIDIZER"), ("peroxide", "OXIDIZER"), ("oxidiz", "OXIDIZER"),
    ("food", "FOOD"), ("meal", "FOOD"), ("perishable", "FOOD"),
    ("laptop", "ELECTRONICS"), ("device", "ELECTRONICS"), ("battery", "ELECTRONICS"), ("electronic", "ELECTRONICS"),
]


def heuristic_psi(request_text: str) -> dict:
    """Rule-based Ψ used only when the LLM is unavailable/invalid or in benchmark mode."""
    text = request_text.lower()
    kappa = "GENERAL"
    for kw, k in _KEYWORDS:
        if kw in text:
            kappa = k
            break
    tmin, tmax = TEMP_ENVELOPES.get(kappa, (-40.0, 60.0))
    priority = 3.0 if any(w in text for w in ("urgent", "emergency", "life", "critical")) else (
        2.0 if kappa in ("PHARMA", "CRYOGENIC") else 1.0
    )
    zones = []
    if "residential" in text:
        zones.append("residential")
    if "no-fly" in text or "no fly" in text:
        zones.append("no-fly")
    dl = 120.0 if "before" in text or "deadline" in text or priority >= 2 else None
    return {
        "kappa": kappa,
        "temp_min": tmin,
        "temp_max": tmax,
        "prohibited_zones": zones,
        "deadline_minutes": dl,
        "ltl": f"◇[0,{int(dl)}] delivered(d')" if dl else "",
        "priority": priority,
        "confidence": 0.3,
    }


async def synthesize(request_text: str) -> dict:
    """Return Ψ(request) with a ``source`` field ("llm" | "fallback" | "benchmark")."""
    if LLM_MODE == "benchmark":
        return {**heuristic_psi(request_text), "source": "benchmark", "raw": None}

    schema = ollama_format_schema(PsiSynthesis)
    user = PSI_SYNTHESIS_V1.format(classes=CLASSES, request=request_text)
    err = None
    for attempt in range(2):
        prompt = user if attempt == 0 else f"{user}\n\nYour previous output was invalid: {err}\nReturn corrected JSON."
        try:
            data = await chat_structured(_SYSTEM, prompt, schema)
            raw = data.pop("_raw", None)
            psi = PsiSynthesis(**data)
            return {**psi.model_dump(), "source": "llm", "raw": raw}
        except (LLMUnavailable, ValidationError) as e:
            err = str(e)[:200]
    return {**heuristic_psi(request_text), "source": "fallback", "error": err, "raw": None}
