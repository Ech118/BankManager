"""P3 e2e setup: make the repo root importable and force mock mode unless a test opts out."""

import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("BM_MODE", "mock")
os.environ.setdefault("BM_LLM", "mock")
logging.getLogger("mcp").setLevel(logging.WARNING)  # the MCP SDK logs every request at INFO
