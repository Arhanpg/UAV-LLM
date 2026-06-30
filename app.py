#!/usr/bin/env python3
"""Legacy entry point — delegates to modular backend."""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.main import app  # noqa: E402, F401

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)
