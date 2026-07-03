"""Pydantic schemas for structured LLM output (Paper 2 Eq. 1 + NL parsing).

Every machine-consumed LLM call is JSON-schema-constrained via Ollama's
``format`` field and then hard-validated against these models before the result
is allowed to reach the algorithm layer (spec §8.3).
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

CLASS_ENUM = ["PHARMA", "FOOD", "ELECTRONICS", "FLAMMABLE", "OXIDIZER", "CRYOGENIC", "GENERAL"]
ACTION_ENUM = [
    "PICKUP",
    "DELIVER",
    "REROUTE",
    "ADD_STOP",
    "REMOVE_STOP",
    "SPLIT_DELIVERY",
    "EMERGENCY_RETURN",
    "INFO",
]


class PsiSynthesis(BaseModel):
    """Ψ(r_i) = ⟨κ_i, τ_i, ρ_i, σ_i⟩ — the constraint tuple (Eq. 1)."""

    kappa: Literal["PHARMA", "FOOD", "ELECTRONICS", "FLAMMABLE", "OXIDIZER", "CRYOGENIC", "GENERAL"]
    temp_min: float = Field(description="τ_min, permissible min temperature °C")
    temp_max: float = Field(description="τ_max, permissible max temperature °C")
    prohibited_zones: List[str] = Field(default_factory=list, description="ρ, geofenced zone names to avoid")
    deadline_minutes: Optional[float] = Field(default=None, description="σ, delivery SLA horizon in minutes")
    ltl: str = Field(default="", description="σ as LTL, e.g. ◇[0,120] delivered(d')")
    priority: float = Field(default=1.0, ge=0.0, le=3.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class MissionAction(BaseModel):
    type: Literal[
        "PICKUP", "DELIVER", "REROUTE", "ADD_STOP", "REMOVE_STOP", "SPLIT_DELIVERY", "EMERGENCY_RETURN", "INFO"
    ]
    location: Optional[str] = None
    package_kappa: Optional[str] = None
    weight_kg: Optional[float] = None
    deadline_minutes: Optional[float] = None
    priority: float = 1.0
    reason: str = ""


class NLParseResult(BaseModel):
    """Parsed structured plan for a pre-flight brief or mid-flight instruction."""

    actions: List[MissionAction] = Field(default_factory=list)
    constraints_detected: List[str] = Field(default_factory=list)
    semantic_cost_impact: Literal["LOW", "MEDIUM", "HIGH", "UNKNOWN"] = "UNKNOWN"
    summary: str = ""
    llm_confidence: float = Field(default=0.5, ge=0.0, le=1.0)


def ollama_format_schema(model: type[BaseModel]) -> dict:
    """JSON schema for Ollama's ``format`` field, inlined (no $ref/$defs)."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def inline(node):
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].split("/")[-1]
                return inline(defs.get(name, {}))
            return {k: inline(v) for k, v in node.items()}
        if isinstance(node, list):
            return [inline(v) for v in node]
        return node

    return inline(schema)
