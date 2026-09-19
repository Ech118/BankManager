"""Composition root: choose fixture or Postgres repositories from MODE.

Specified by docs/mcp-tools.md and docs/adr/0007.

This is the ONLY module in mcp_server/ that knows which implementation is in
use. Every tool takes a repository Protocol, so swapping the backend changes
nothing above this line.

TODO(roadmap Step 1, P1).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from schema.contracts.interfaces import FactRepository, FilingRepository, MarketRepository


@dataclass(frozen=True)
class Backends:
    """The three repositories a tool may be given."""

    facts: FactRepository
    filings: FilingRepository
    market: MarketRepository


def mode() -> str:
    """Current MODE. `mock` unless explicitly set to `live`."""
    return os.environ.get("MODE", os.environ.get("BM_MODE", "mock")).lower()


def build_backends() -> Backends:
    """Fixture-backed repositories in mock mode, Postgres-backed in live mode.

    Mock mode must not require DATABASE_URL, a running Postgres, or any API key
    (decision 6): a teammate with a fresh clone runs the whole pipeline offline.
    """
    raise NotImplementedError("TODO(roadmap Step 1, P1)")
