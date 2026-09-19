"""Shared test setup for the contract tests."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Remember what the caller asked for BEFORE we force mock mode for most tests.
# MODE is the current name; BM_MODE is still read so older shells keep working.
ORIGINAL_MODE = os.environ.get("MODE", os.environ.get("BM_MODE", "mock")).lower()

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _force_mock(request, monkeypatch):
    """Every test runs in mock mode unless it is marked @pytest.mark.live."""
    if request.node.get_closest_marker("live") is None:
        monkeypatch.setenv("MODE", "mock")
        monkeypatch.setenv("LLM_MODE", "mock")
        monkeypatch.setenv("BM_MODE", "mock")
        monkeypatch.setenv("BM_LLM", "mock")


def pytest_configure(config):
    config.addinivalue_line("markers", "live: needs MODE=live and real API keys")
