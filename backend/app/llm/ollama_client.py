"""Ollama HTTP bridge — upgraded in Phase 3 with structured outputs."""

import json

import httpx

from app.config import CLASSES, OLLAMA_BASE_URL, OLLAMA_MODEL


async def ollama_chat(prompt: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=35.0) as cli:
            r = await cli.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": 900},
                },
            )
            if r.status_code == 200:
                return r.json().get("response", "")
    except Exception as e:
        return f"[LLM offline — {e}]"
    return ""


async def llm_parse_nl(instruction, city_labels, classes=None) -> dict:
    classes = classes or CLASSES
    prompt = f"""You are a UAV mission planner AI for Dharwad/Hubli region, India.
Parse the natural language instruction into structured JSON.

Available locations: {city_labels}
Cargo classes: {classes}
Safety rules: FLAMMABLE+OXIDIZER cannot co-fly. CRYOGENIC+ELECTRONICS cannot co-fly.

Instruction: \"{instruction}\"

Output ONLY valid JSON (no markdown):
{{"actions":[{{"type":"PICKUP|DELIVER|REROUTE|ABORT|EMERGENCY_RETURN|STATUS",
  "location":"location name or null","package_kappa":"class or null",
  "weight_kg":2.0,"reason":"brief","deadline_minutes":null,"priority":1.0}}],
"constraints_detected":["cold-chain","deadline"],
"semantic_cost_impact":"LOW|MEDIUM|HIGH","llm_confidence":0.9}}"""
    raw = await ollama_chat(prompt)
    try:
        s = raw.find("{")
        e = raw.rfind("}") + 1
        if s >= 0 and e > s:
            return json.loads(raw[s:e])
    except json.JSONDecodeError:
        pass
    dl = instruction.lower()
    kappa = "GENERAL"
    for kw, k in [
        ("insulin", "PHARMA"),
        ("medicine", "PHARMA"),
        ("pharma", "PHARMA"),
        ("fuel", "FLAMMABLE"),
        ("oxygen", "OXIDIZER"),
        ("cryo", "CRYOGENIC"),
        ("food", "FOOD"),
        ("laptop", "ELECTRONICS"),
        ("device", "ELECTRONICS"),
    ]:
        if kw in dl:
            kappa = k
            break
    action = "STATUS"
    if any(w in dl for w in ["pickup", "pick up", "collect", "grab"]):
        action = "PICKUP"
    elif any(w in dl for w in ["deliver", "drop", "bring"]):
        action = "DELIVER"
    elif any(w in dl for w in ["return", "emergency", "abort"]):
        action = "EMERGENCY_RETURN"
    elif any(w in dl for w in ["reroute", "avoid", "go to"]):
        action = "REROUTE"
    return {
        "actions": [{"type": action, "location": None, "package_kappa": kappa, "reason": "heuristic fallback", "priority": 1.0}],
        "constraints_detected": [],
        "semantic_cost_impact": "UNKNOWN",
        "llm_confidence": 0.3,
    }


async def llm_plan(instruction, city_labels) -> dict:
    prompt = f"""You are a UAV mission planner for Dharwad-Hubli, Karnataka, India.
Depot: {city_labels[0] if city_labels else 'Depot'}
Waypoints: {city_labels[1:]}
Mission: \"{instruction}\"
Output ONLY valid JSON:
{{"mission_name":"short name",
  "waypoints":[{{"location":"exact name","action":"PICKUP|DELIVER",
    "package_description":"item","weight_kg":2.0,
    "kappa":"PHARMA|FOOD|ELECTRONICS|FLAMMABLE|OXIDIZER|CRYOGENIC|GENERAL",
    "deadline_minutes":30}}],
  "total_estimated_time_minutes":45,
  "risk_flags":["incompatible cargo"],
  "llm_reasoning":"brief explanation"}}"""
    raw = await ollama_chat(prompt)
    try:
        s = raw.find("{")
        e = raw.rfind("}") + 1
        if s >= 0 and e > s:
            return json.loads(raw[s:e])
    except json.JSONDecodeError:
        pass
    return {"mission_name": "Auto Plan", "waypoints": [], "risk_flags": [], "llm_reasoning": raw[:300] if raw else "No response"}
