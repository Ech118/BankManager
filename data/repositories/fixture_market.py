"""Fixture-backed MarketRepository. Powers MODE=mock with no database.

Specified by schema/contracts/interfaces.py (MarketRepository).

TODO(roadmap Step 4, P1).
"""

from __future__ import annotations

from schema.contracts.common import ISODate, Ticker
from schema.contracts.market import CompanyProfile, MarketSnapshot, NewsItem, Peer


class FixtureMarketRepository:
    """In-memory MarketRepository over fixtures/mock/."""

    def __init__(self, fixtures_dir: str | None = None) -> None:
        self.fixtures_dir = fixtures_dir
        raise NotImplementedError("TODO(roadmap Step 4, P1)")

    def get_snapshot(self, ticker: Ticker, as_of: ISODate) -> MarketSnapshot | None:
        raise NotImplementedError("TODO(roadmap Step 4, P1)")

    def get_profile(self, ticker: Ticker, as_of: ISODate) -> CompanyProfile | None:
        raise NotImplementedError("TODO(roadmap Step 4, P1)")

    def get_peers(self, ticker: Ticker, as_of: ISODate, *, limit: int = 6) -> list[Peer]:
        raise NotImplementedError("TODO(roadmap Step 4, P1)")

    def search_news(
        self, ticker: Ticker, as_of: ISODate, *, lookback_days: int = 60, limit: int = 20
    ) -> list[NewsItem]:
        raise NotImplementedError("TODO(roadmap Step 4, P1)")
