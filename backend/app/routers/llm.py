"""Natural-language instruction endpoint (spec §8.1, §8.8)."""

from fastapi import APIRouter

from app.config import OLLAMA_MODEL
from app.llm.nl_mission_parser import parse as nl_parse
from app.services.mission_service import SESSIONS
from app.ws.telemetry import emit, session_context

router = APIRouter(prefix="/api", tags=["llm"])


@router.post("/llm/instruction")
async def instruction(req: dict):
    session_id = req.get("session_id", "default")
    text = req.get("instruction", "")
    phase = "preflight" if req.get("phase") in ("initial", "preflight") else "midflight"
    sess = SESSIONS.get(session_id) or {}
    city_labels = [c.label for c in sess.get("city", [])]

    with session_context(session_id):
        emit("llm_prompt_sent", scope="instruction", text=text, phase=phase)
        result = await nl_parse(text, city_labels, phase)
        raw = result.get("raw") or {}
        emit("llm_response_received", scope="instruction", source=result.get("source"), response=raw.get("response"))

    return {"instruction": text, "phase": phase, "result": result, "ollama_model": OLLAMA_MODEL}
