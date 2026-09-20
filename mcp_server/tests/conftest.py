"""Test setup for the MCP server suite.

Forces mock mode so these tests never touch the network or a database, and puts
the repo root on sys.path so `schema.contracts`, `data` and `mcp_server` import.

The one exception is a test marked `live`, which exists precisely to talk to
SEC and the market provider over a real stdio subprocess. It is skipped unless
BM_LIVE_TESTS=1, so a clone with no keys still runs the whole suite offline.

The `live` marker is registered here rather than in a pytest.ini because the
repo root belongs to no partition (CLAUDE.md); a conftest in P1's own test
directory does the same job without touching shared files.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "live: talks to SEC and the market provider. Needs BM_LIVE_TESTS=1 and "
        "real keys; skipped otherwise.",
    )


@pytest.fixture(autouse=True)
def _force_mock(request, monkeypatch):
    if request.node.get_closest_marker("live"):
        return
    monkeypatch.setenv("MODE", "mock")
    monkeypatch.setenv("LLM_MODE", "mock")
