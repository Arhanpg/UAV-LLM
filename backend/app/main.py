"""FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.routers import data, llm, mission
from app.routers.stress import router as stress_router

app = FastAPI(title="UAV-LLM", version="0.4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(data.router)
app.include_router(llm.router)
app.include_router(mission.router)
app.include_router(stress_router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.4.0"}
