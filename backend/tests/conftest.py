"""Test configuration.

Force benchmark LLM mode before any app module is imported so the test suite
never depends on a running Ollama server (CI has no GPU/model). The live LLM
path is exercised manually / in the demo, not in unit tests.
"""

import os

os.environ.setdefault("LLM_MODE", "benchmark")

from app.models.db import init_db  # noqa: E402

init_db()
