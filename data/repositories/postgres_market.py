"""Postgres MarketRepository. MODE=live only.

Specified by schema/contracts/interfaces.py (MarketRepository).

Market data is not immutable, so rows are keyed by (ticker, as_of) and a read
returns the newest snapshot at or before the requested date. A missing snapshot
returns None, which the caller turns into an `unavailable` ValueObject plus a
data_quality gap - never into a stale price silently presented as current.

TODO(roadmap Step 4, P1).
"""

from __future__ import annotations

from schema.contracts.common import ISODate, Ticker
from schema.contracts.market import CompanyProfile, MarketSnapshot, NewsItem, Peer


class PostgresMarketRepository:
    """MarketRepository backed by the market_snapshots, peers and news tables."""

    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = dsn
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
