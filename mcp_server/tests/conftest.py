"""Test setup for the MCP server suite.

Forces mock mode so these tests never touch the network or a database, and puts
the repo root on sys.path so `schema.contracts`, `data` and `mcp_server` import.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _force_mock(monkeypatch):
    monkeypatch.setenv("MODE", "mock")
    monkeypatch.setenv("LLM_MODE", "mock")
