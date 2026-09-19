"""Fixture-backed MarketRepository. Powers MODE=mock with no database.

Specified by schema/contracts/interfaces.py (MarketRepository).

Market data is not immutable, so every record carries the instant it was
observed. A read returns the newest record observed on or before `as_of`, and
nothing at all when none had been observed yet - never a later price presented
as if it were current.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from schema.contracts.common import ISODate, Ticker
from schema.contracts.market import CompanyProfile, MarketSnapshot, NewsItem, Peer

_DEFAULT_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "mock"


def _day(timestamp: str) -> str:
    """Date part of an ISO timestamp or date, for comparison against `as_of`."""
    return timestamp[:10]


class FixtureMarketRepository:
    """In-memory MarketRepository over fixtures/mock/."""

    def __init__(self, fixtures_dir: str | Path | None = None) -> None:
        self.fixtures_dir = Path(fixtures_dir) if fixtures_dir else _DEFAULT_FIXTURES
        self._snapshot = MarketSnapshot.model_validate(self._load("market_snapshot.json"))
        self._profile = CompanyProfile.model_validate(self._load("company_profile.json"))
        self._peers = [Peer.model_validate(p) for p in self._load("peers.json")]
        self._news = [
            NewsItem.model_validate(n) for n in self._load("factsheet.json")["news"]
        ]

    def _load(self, name: str):
        return json.loads((self.fixtures_dir / name).read_text(encoding="utf-8"))

    # ------------------------------------------------------------------
    # MarketRepository
    # ------------------------------------------------------------------
    def get_snapshot(self, ticker: Ticker, as_of: ISODate) -> MarketSnapshot | None:
        """Price, shares and the EV bridge as observed on or before `as_of`.

        Returns None rather than a stale snapshot: the caller turns that into an
        `unavailable` value plus a data_quality gap, which is visible, where a
        silently-reused old price would not be.
        """
        if self._snapshot.ticker != ticker:
            return None
        if as_of and _day(self._snapshot.as_of) > as_of:
            return None
        return self._snapshot

    def get_profile(self, ticker: Ticker, as_of: ISODate) -> CompanyProfile | None:
        """Identity and SIC classification, which drives check_scope."""
        if self._profile.ticker != ticker:
            return None
        if as_of and self._profile.as_of > as_of:
            return None
        return self._profile

    def get_peers(self, ticker: Ticker, as_of: ISODate, *, limit: int = 6) -> list[Peer]:
        """Comparable companies. The fixture set is fixed and SIC-matched."""
        if self._profile.ticker != ticker:
            return []
        return self._peers[:limit]

    def search_news(
        self, ticker: Ticker, as_of: ISODate, *, lookback_days: int = 60, limit: int = 20
    ) -> list[NewsItem]:
        """Headlines published in [as_of - lookback_days, as_of], newest first.

        The upper bound matters as much as the lower one: a backtest that sees
        tomorrow's headlines is not a backtest.
        """
        if self._profile.ticker != ticker:
            return []
        items = sorted(self._news, key=lambda n: n.date, reverse=True)
        if as_of:
            floor = (date.fromisoformat(as_of) - timedelta(days=lookback_days)).isoformat()
            items = [n for n in items if floor <= n.date <= as_of]
        return items[:limit]
