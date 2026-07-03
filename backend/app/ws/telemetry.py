"""In-process telemetry event bus + WebSocket fan-out (Phase 4, spec §8.6).

Algorithm/LLM/verifier code emits events via the context-scoped ``emit`` helper;
they are buffered per session and pushed live to any WebSocket subscribers. The
``emit`` call is a safe no-op when no session context is active (e.g. in unit
tests), so the math modules stay decoupled from the transport.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import time
from typing import Optional

# Event types streamed to the glass-box UI (spec §7, Phase 4).
EVENT_TYPES = [
    "session_start",
    "phase1_step",
    "phase1_complete",
    "phase2_subtrajectory_attempt",
    "phase2_mst_built",
    "phase2_refine_result",
    "llm_prompt_sent",
    "llm_response_received",
    "psi_synthesis_result",
    "smt_verify_result",
    "route_finalized",
    "disruption_detected",
    "replan_start",
    "replan_complete",
]

_current_session: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("session", default=None)


class TelemetryBus:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = {}
        self._buffer: dict[str, list] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, sid: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subs.setdefault(sid, set()).add(q)
        for evt in self._buffer.get(sid, []):  # replay history to new subscriber
            q.put_nowait(evt)
        return q

    def unsubscribe(self, sid: str, q: asyncio.Queue) -> None:
        self._subs.get(sid, set()).discard(q)

    def emit(self, sid: str, type_: str, **data) -> None:
        evt = {"type": type_, "t": round(time.time(), 3), **data}
        buf = self._buffer.setdefault(sid, [])
        buf.append(evt)
        del buf[:-800]  # cap history
        for q in list(self._subs.get(sid, ())):
            if self._loop is not None:
                self._loop.call_soon_threadsafe(q.put_nowait, evt)
            else:
                with contextlib.suppress(Exception):
                    q.put_nowait(evt)

    def history(self, sid: str) -> list:
        return list(self._buffer.get(sid, []))


bus = TelemetryBus()


@contextlib.contextmanager
def session_context(sid: str):
    token = _current_session.set(sid)
    try:
        bus.emit(sid, "session_start", session_id=sid)
        yield
    finally:
        _current_session.reset(token)


def emit(type_: str, **data) -> None:
    """Emit an event for the active session context (no-op if none)."""
    sid = _current_session.get()
    if sid is not None:
        bus.emit(sid, type_, **data)
