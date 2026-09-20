"""Shared fixtures for P1's unit tests.

Every test in this directory runs offline. The cache redirect is autouse
because a module that reaches the network on a miss would otherwise write into
the developer's real `.cache/edgar` - and, worse, could PASS from a warm cache
on one machine and fail on a clean clone.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Point the on-disk cache at a per-test directory."""
    monkeypatch.setenv("BM_CACHE_DIR", str(tmp_path / "cache"))
    yield


@pytest.fixture(autouse=True)
def no_installed_market_client():
    """Reset the module-level market client between tests."""
    from data.ingest import market_client

    market_client.set_client(None)
    yield
    market_client.set_client(None)
