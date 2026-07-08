"""FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.routers import data, llm, mission
from app.routers.compare import router as compare_router
from app.routers.replan import router as replan_router
from app.routers.stress import router as stress_router
from app.routers.testcases import router as testcases_router

app = FastAPI(
    title="UAV-LLM Mission Control",
    version="0.5.0",
    description="Semantic UAV Delivery Planner -- Dharwad/Hubli",
)

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
app.include_router(testcases_router)
app.include_router(compare_router)
app.include_router(replan_router)


@app.get("/", include_in_schema=False)
async def root():
    """Redirect browser to interactive API docs."""
    return RedirectResponse(url="/docs")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.5.0"}
