"""FastAPI application entry point (Phase 4).

Includes the mission/llm/data routers, a WebSocket telemetry endpoint that
streams the glass-box event bus per session, and startup hooks that initialize
SQLite and bind the telemetry bus to the running event loop.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL, LLM_MODE
from app.models.db import init_db
from app.routers import data as data_router
from app.routers import llm as llm_router
from app.routers import mission as mission_router
from app.services.mission_service import SESSIONS
from app.ws.telemetry import bus


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    bus.bind_loop(asyncio.get_running_loop())
    yield


app = FastAPI(title="UAV-LLM — Semantic Multi-Commodity UAV Delivery", version="1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(mission_router.router)
app.include_router(llm_router.router)
app.include_router(data_router.router)

ROOT_INDEX = Path(__file__).resolve().parents[2] / "index.html"


@app.get("/")
async def root():
    if ROOT_INDEX.exists():
        return FileResponse(str(ROOT_INDEX))
    return {"message": "UAV-LLM API — React frontend at http://localhost:5173"}


@app.get("/health")
async def health():
    try:
        async with httpx.AsyncClient(timeout=2.5) as cli:
            r = await cli.get(f"{OLLAMA_BASE_URL}/api/tags")
            ok = r.status_code == 200
            models = [m["name"] for m in r.json().get("models", [])] if ok else []
    except Exception:
        ok, models = False, []
    return {
        "status": "ok",
        "ollama": ok,
        "model": OLLAMA_MODEL,
        "llm_mode": LLM_MODE,
        "models": models,
        "sessions": len(SESSIONS),
        "city": "Dharwad-Hubli, Karnataka",
    }


@app.websocket("/ws/mission/{session_id}")
async def ws_mission(ws: WebSocket, session_id: str):
    """Stream live glass-box telemetry for a session (spec §7, Phase 4)."""
    await ws.accept()
    q = bus.subscribe(session_id)
    try:
        while True:
            evt = await q.get()
            await ws.send_json(evt)
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(session_id, q)
