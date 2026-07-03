"""SQLite persistence via SQLModel (Phase 4).

Missions are deterministic in their GenConfig (seed-driven world generation), so
we persist the config + a result summary keyed by session_id. That is enough to
list mission history, replay a mission, and rehydrate the full world after a
server restart (by re-running generation from the stored config).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, Session, SQLModel, create_engine, select

from app.config import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})


class MissionRecord(SQLModel, table=True):
    session_id: str = Field(primary_key=True)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    config_json: str = ""
    summary_json: str = ""


def init_db() -> None:
    from app.config import DATA_DIR

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)


def save_mission(session_id: str, config: dict, summary: dict) -> None:
    with Session(engine) as s:
        rec = s.get(MissionRecord, session_id)
        if rec is None:
            rec = MissionRecord(session_id=session_id)
        rec.config_json = json.dumps(config)
        rec.summary_json = json.dumps(summary)
        s.add(rec)
        s.commit()


def get_mission(session_id: str) -> Optional[dict]:
    with Session(engine) as s:
        rec = s.get(MissionRecord, session_id)
        if rec is None:
            return None
        return {
            "session_id": rec.session_id,
            "created_at": rec.created_at,
            "config": json.loads(rec.config_json or "{}"),
            "summary": json.loads(rec.summary_json or "{}"),
        }


def list_missions(limit: int = 50) -> list[dict]:
    with Session(engine) as s:
        rows = s.exec(select(MissionRecord).order_by(MissionRecord.created_at.desc()).limit(limit)).all()
        return [
            {"session_id": r.session_id, "created_at": r.created_at, "summary": json.loads(r.summary_json or "{}")}
            for r in rows
        ]
