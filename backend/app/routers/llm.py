"""Natural-language instruction endpoint (spec SS8.1, SS8.8)."""

from fastapi import APIRouter

from app.config import OLLAMA_MODEL
from app.geo.locations import load_locations
from app.llm.nl_mission_parser import parse as nl_parse
from app.services.mission_service import SESSIONS
from app.ws.telemetry import emit, session_context

router = APIRouter(prefix="/api", tags=["llm"])

# Full catalog label list -- built once at import time
_ALL_LOCATION_LABELS: list[str] = [r[0] for r in load_locations()]


@router.post("/llm/instruction")
async def instruction(req: dict):
    session_id = req.get("session_id", "default")
    text = req.get("instruction", "")
    phase = "preflight" if req.get("phase") in ("initial", "preflight") else "midflight"
    sess = SESSIONS.get(session_id) or {}
    session_city_labels = [c.label for c in sess.get("city", [])]

    # Merge: active session nodes FIRST (so the router can act on them),
    # then the rest of the catalog so the LLM can match any known place.
    seen: set[str] = set(session_city_labels)
    full_labels = session_city_labels + [
        lbl for lbl in _ALL_LOCATION_LABELS if lbl not in seen
    ]

    with session_context(session_id):
        emit("llm_prompt_sent", scope="instruction", text=text, phase=phase)
        result = await nl_parse(text, full_labels, phase)
        raw = result.get("raw") or {}
        emit("llm_response_received", scope="instruction",
             source=result.get("source"), response=raw.get("response"))

    return {"instruction": text, "phase": phase, "result": result, "ollama_model": OLLAMA_MODEL}
