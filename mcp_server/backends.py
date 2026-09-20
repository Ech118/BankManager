"""Composition root: choose fixture or Postgres repositories from MODE.

Specified by docs/mcp-tools.md and docs/adr/0007.

This is the ONLY module in mcp_server/ that knows which implementation is in
use. Every tool takes repositories by injection, so swapping the backend
changes nothing above this line.

MODE=mock must not require DATABASE_URL, a running Postgres, or any API key: a
teammate with a fresh clone runs the whole pipeline offline.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from schema.contracts.interfaces import FactRepository, FilingRepository, MarketRepository


@dataclass(frozen=True)
class Backends:
    """The repositories a tool may be given.

    `filings` is populated in mock mode from the fixture sections. It stays
    None only where a backend genuinely has no filing store; the tools that
    need it are not registered in that case.
    """

    facts: FactRepository
    market: MarketRepository
    filings: FilingRepository | None = None


def mode() -> str:
    """Current MODE. `mock` unless explicitly set to `live`."""
    return os.environ.get("MODE", os.environ.get("BM_MODE", "mock")).lower()


def build_backends(fixtures_dir: str | Path | None = None) -> Backends:
    """Fixture-backed repositories in mock mode, Postgres-backed in live mode."""
    if mode() == "live":
        # Computed on demand from EDGAR and the market provider, memoised per
        # process. Nothing above this line changes - which is what the
        # Protocols are for (ADR 0007).
        from data.repositories.live import (
            LiveFactRepository,
            LiveFilingRepository,
            LiveMarketRepository,
        )

        return Backends(
            facts=LiveFactRepository(),
            market=LiveMarketRepository(),
            filings=LiveFilingRepository(),
        )

    from data.repositories.fixture_facts import FixtureFactRepository
    from data.repositories.fixture_filings import FixtureFilingRepository
    from data.repositories.fixture_market import FixtureMarketRepository

    return Backends(
        facts=FixtureFactRepository(fixtures_dir),
        market=FixtureMarketRepository(fixtures_dir),
        filings=FixtureFilingRepository(fixtures_dir),
    )


def require_in_scope(ticker: str, as_of: str | None = None) -> None:
    """Refuse an out-of-scope ticker before any data is fetched.

    Raises ValueError naming the ticker and the reason. The message surfaces in
    the UI, so it has to read as an explanation rather than a status code.
    """
    from data import api as data_api

    scope: dict[str, Any] = data_api.check_scope(ticker, as_of)
    if not scope["in_scope"]:
        raise ValueError(f"{ticker}: {scope['reason']}")
