"""Versioned prompt templates (kept out of call-site code, spec §8.3)."""

from app.llm.prompts.templates import (
    MISSION_BRIEF_V1,
    NL_INSTRUCTION_V1,
    PSI_SYNTHESIS_V1,
)

__all__ = ["PSI_SYNTHESIS_V1", "NL_INSTRUCTION_V1", "MISSION_BRIEF_V1"]
