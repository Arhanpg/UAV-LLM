from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class GenConfig(BaseModel):
    loc_indices: List[int] = list(range(12))
    pkg_requests: List[dict] = []
    seed: int = 42
    incompat_density: float = 0.25
    n_gfz: int = 3
    deadline_tight: float = 0.65
    hazard_mix: float = 0.50
    cap_ratio: float = 0.35
    wind_dir: float = 270.0
    llm_error: float = 0.10


class NLReq(BaseModel):
    instruction: str
    session_id: str = "default"
    phase: str = "midflight"


class ReplanReq(BaseModel):
    session_id: str
    disruption: dict


class SessionRecord(BaseModel):
    session_id: str
    payload: Dict[str, Any]


class SessionStore:
    """In-memory session store — replaced by SQLite in Phase 4."""

    def __init__(self) -> None:
        self._sessions: Dict[str, dict] = {}

    def get(self, session_id: str) -> Optional[dict]:
        return self._sessions.get(session_id)

    def set(self, session_id: str, data: dict) -> None:
        self._sessions[session_id] = data

    def __len__(self) -> int:
        return len(self._sessions)
