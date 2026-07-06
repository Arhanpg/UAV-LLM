"""Mission generation + replanning endpoints (spec §8.1)."""

from fastapi import APIRouter, HTTPException

from app.models.db import get_mission, list_missions
from app.models.session import GenConfig, ReplanReq
from app.services.mission_service import generate_mission, replan_mission

router = APIRouter(prefix="/api", tags=["mission"])


@router.post("/mission/generate")
async def mission_generate(cfg: GenConfig):
    return await generate_mission(cfg)


# Legacy alias so the standalone index.html keeps working.
@router.post("/generate")
async def generate_alias(cfg: GenConfig):
    return await generate_mission(cfg)


@router.post("/mission/replan")
async def mission_replan(req: ReplanReq):
    disruption = dict(req.disruption)
    summary = req.instruction
    if req.instruction and not disruption:
        # Free-text NL disruption → default no-fly zone near the map centre.
        disruption = {"type": "storm", "x": 0.0, "y": 0.0, "r": 220.0}
    try:
        return replan_mission(req.session_id, disruption, req.flown_steps, summary)
    except KeyError:
        raise HTTPException(404, "Session not found")


@router.post("/replan")
async def replan_alias(req: ReplanReq):
    return await mission_replan(req)


@router.get("/missions")
async def missions_history(limit: int = 50):
    return {"missions": list_missions(limit)}


@router.get("/mission/{session_id}")
async def mission_detail(session_id: str):
    rec = get_mission(session_id)
    if not rec:
        raise HTTPException(404, "Session not found")
    return rec
