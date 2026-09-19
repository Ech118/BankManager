"""Dev/demo composition root: the real Coordinator and server over the MCP test double.

For local demos only. It wires the FastAPI server to `fake_mcp` (fixture data over real MCP) and
mock LLM outputs, and slows each model call so the parallel agent lanes are visible in the UI.

    uvicorn tests.e2e.support.dev_app:app --port 8000        # then: cd web && npm run dev

BM_DEV_DELAY=<seconds> sets the per-call delay (default 1.5; 0 disables it).
"""

from __future__ import annotations

import logging
import os
import time

from agents import client
from orchestrator import server
from orchestrator.mcp_client import InMemoryMcpClient
from tests.e2e.support.fake_mcp import build_fake_server

logging.getLogger("mcp").setLevel(logging.WARNING)
_DELAY = float(os.environ.get("BM_DEV_DELAY", "1.5"))
_real_complete = client.complete


def _slow_complete(*args, **kwargs):
    time.sleep(_DELAY)
    return _real_complete(*args, **kwargs)


if _DELAY > 0:
    client.complete = _slow_complete

server.configure(lambda: InMemoryMcpClient(build_fake_server()))
app = server.create_app()
