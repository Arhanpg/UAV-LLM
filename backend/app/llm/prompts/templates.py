"""Prompt templates. Bump the _Vn suffix when a template changes materially."""

PSI_SYNTHESIS_V1 = """You are the constraint-synthesis layer (Ψ) of a UAV delivery planner.
Read one natural-language delivery request and extract its implicit
safety-critical constraints as structured data.

Commodity classes (κ): {classes}
Temperature-sensitive classes require a strict thermal envelope (τ).
Rules of thumb: insulin/vaccines/medicine -> PHARMA (2 to 8 °C);
frozen/cryo samples -> CRYOGENIC (-196 to -50 °C); fuel/solvent -> FLAMMABLE;
oxygen/peroxide -> OXIDIZER; perishable food -> FOOD (0 to 25 °C);
devices/laptops/batteries -> ELECTRONICS; anything else -> GENERAL.

Request: "{request}"

Return the commodity class κ, the permissible temperature range [τ_min, τ_max]
in °C, any prohibited/geofenced zones ρ named in the request (short names like
"residential" or "no-fly"), the delivery deadline as a POSITIVE number of
minutes from now σ (use null if the request gives no relative deadline — never
0), an LTL form of the SLA, a priority (1=normal, 2=urgent, 3=life-critical),
and your confidence 0..1."""

NL_INSTRUCTION_V1 = """You are the mission parser for a UAV delivery system in Dharwad-Hubli, India.
Convert the operator's {phase} instruction into a structured action list.

Known locations: {locations}
Commodity classes: {classes}
Action types: PICKUP, DELIVER, REROUTE, ADD_STOP, REMOVE_STOP, SPLIT_DELIVERY,
EMERGENCY_RETURN, INFO.
SPLIT_DELIVERY = hand off the final leg to a ground agent (used when a zone
becomes unreachable but the payload must still arrive, e.g. cold-chain insulin).

Instruction: "{instruction}"

Emit one action per intent, each with a location (exact known name or null),
package_kappa, weight_kg, deadline_minutes, priority, and a short reason. Also
list constraints_detected, an overall semantic_cost_impact
(LOW/MEDIUM/HIGH), a one-line summary, and llm_confidence 0..1."""

MISSION_BRIEF_V1 = """You are planning a UAV pickup-and-delivery mission in Dharwad-Hubli, India.
Depot: {depot}. Available waypoints: {waypoints}.

Operator brief: "{instruction}"

Produce an ordered action list (PICKUP/DELIVER with location, package_kappa,
weight_kg, deadline_minutes, priority, reason), the constraints you detected,
the overall semantic_cost_impact, a one-line summary, and llm_confidence."""
