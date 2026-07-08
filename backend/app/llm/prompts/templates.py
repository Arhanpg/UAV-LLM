"""Prompt templates. Bump the _Vn suffix when a template changes materially."""

PSI_SYNTHESIS_V1 = """You are the constraint-synthesis layer (PSI) of a UAV delivery planner.
Read one natural-language delivery request and extract its implicit
safety-critical constraints as structured data.

Commodity classes (kappa): {classes}
Temperature-sensitive classes require a strict thermal envelope (tau).
Rules of thumb: insulin/vaccines/medicine -> PHARMA (2 to 8 deg C);
frozen/cryo samples -> CRYOGENIC (-196 to -50 deg C); fuel/solvent -> FLAMMABLE;
oxygen/peroxide -> OXIDIZER; perishable food/dairy/milk -> FOOD (0 to 25 deg C);
devices/laptops/batteries -> ELECTRONICS; anything else -> GENERAL.

Request: "{request}"

Return the commodity class kappa, the permissible temperature range [tau_min, tau_max]
in deg C, any prohibited/geofenced zones rho named in the request (short names like
"residential" or "no-fly"), the delivery deadline as a POSITIVE number of
minutes from now sigma (use null if the request gives no relative deadline -- never
0), an LTL form of the SLA, a priority (1=normal, 2=urgent, 3=life-critical),
and your confidence 0..1."""

NL_INSTRUCTION_V1 = """You are the mission parser for a UAV delivery system in Dharwad-Hubli, India.
Convert the operator's {phase} instruction into a structured action list.

Known locations (use EXACT names from this list only): {locations}
Commodity classes: {classes}
Action types: PICKUP, DELIVER, REROUTE, ADD_STOP, REMOVE_STOP, SPLIT_DELIVERY,
EMERGENCY_RETURN, INFO.

COMMODITY CLASS RULES:
- milk / dairy / curd / butter / paneer / nandini / kmf -> FOOD
- medicine / insulin / vaccine / tablet / capsule / injection -> PHARMA
- laptop / phone / mobile / charger / device -> ELECTRONICS
- fuel / petrol / diesel / solvent -> FLAMMABLE
- oxygen / peroxide -> OXIDIZER
- nitrogen / cryo / liquid nitrogen -> CRYOGENIC
- notebooks / books / documents / clothes / general items -> GENERAL
- Never output free-text as package_kappa -- always map to one of: {classes}

QUANTITY RULES:
- "2 L milk" -> weight_kg = 2.0, package_kappa = FOOD
- "3 notebooks" -> weight_kg = 0.9, package_kappa = GENERAL
- "500ml water" -> weight_kg = 0.5, package_kappa = FOOD
- "5 kg rice" -> weight_kg = 5.0, package_kappa = FOOD

ACTION RULES:
- "go through X" / "via X" / "pass through X" / "stop at X" -> ADD_STOP, location = X
- "pick up" / "collect" / "get" / "fetch" / "grab" from X -> PICKUP, location = X
- "deliver" / "give" / "bring" / "drop" / "send" to X -> DELIVER, location = X
- If instruction says "go through X AND give/deliver to Y": emit TWO actions:
  1. ADD_STOP for X  2. DELIVER for Y
- SPLIT_DELIVERY = hand off to a ground agent when zone unreachable (e.g. cold-chain insulin)

Instruction: "{instruction}"

Emit one action per intent. For each action include: type, location (exact name from
the list above or null), package_kappa (must be one of {classes}), weight_kg,
deadline_minutes, priority (1.0 normal / 2.0 urgent / 3.0 life-critical), reason.
Also list constraints_detected, semantic_cost_impact (LOW/MEDIUM/HIGH),
a one-line summary, and llm_confidence 0..1."""

MISSION_BRIEF_V1 = """You are planning a UAV pickup-and-delivery mission in Dharwad-Hubli, India.
Depot: {depot}. Available waypoints: {waypoints}.

Operator brief: "{instruction}"

Produce an ordered action list (PICKUP/DELIVER with location, package_kappa,
weight_kg, deadline_minutes, priority, reason), the constraints you detected,
the overall semantic_cost_impact, a one-line summary, and llm_confidence."""
