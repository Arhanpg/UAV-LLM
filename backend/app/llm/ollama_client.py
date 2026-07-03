"""Ollama HTTP bridge — schema-constrained structured outputs (Phase 3, spec §8.3).

Every machine-consumed call goes through ``chat_structured``, which uses Ollama's
``/api/chat`` with a JSON-schema ``format`` so the model can only emit output that
matches the schema. Thinking is disabled for structured calls to keep responses
clean and fast. Free-text (human-facing) prose uses ``chat_text``.
"""

from __future__ import annotations

import json
from typing import Optional

import httpx

from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL


class LLMUnavailable(RuntimeError):
    """Raised when Ollama cannot be reached or returns an unusable response."""


async def available() -> bool:
    try:
        async with httpx.AsyncClient(timeout=2.5) as cli:
            r = await cli.get(f"{OLLAMA_BASE_URL}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


async def list_models() -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=2.5) as cli:
            r = await cli.get(f"{OLLAMA_BASE_URL}/api/tags")
            if r.status_code == 200:
                return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        pass
    return []


async def chat_structured(
    system: str,
    user: str,
    schema: dict,
    model: Optional[str] = None,
    temperature: float = 0.1,
    timeout: float = 90.0,
) -> dict:
    """Return a dict validated against ``schema`` (raises LLMUnavailable on failure).

    The raw request/response are attached under ``_raw`` for the glass-box UI.
    """
    model = model or OLLAMA_MODEL
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "think": False,
        "format": schema,
        "options": {"temperature": temperature},
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as cli:
            r = await cli.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
    except Exception as e:
        raise LLMUnavailable(f"Ollama request failed: {e}") from e
    if r.status_code != 200:
        raise LLMUnavailable(f"Ollama HTTP {r.status_code}: {r.text[:200]}")
    content = r.json().get("message", {}).get("content", "")
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise LLMUnavailable(f"Non-JSON structured output: {content[:200]}") from e
    data["_raw"] = {"model": model, "prompt": user, "system": system, "response": content}
    return data


async def chat_text(prompt: str, model: Optional[str] = None, timeout: float = 60.0) -> str:
    """Free-text generation for human-facing prose only."""
    model = model or OLLAMA_MODEL
    try:
        async with httpx.AsyncClient(timeout=timeout) as cli:
            r = await cli.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False, "think": False,
                      "options": {"temperature": 0.2, "num_predict": 400}},
            )
            if r.status_code == 200:
                return r.json().get("response", "")
    except Exception as e:
        raise LLMUnavailable(f"Ollama request failed: {e}") from e
    raise LLMUnavailable(f"Ollama HTTP {r.status_code}")
