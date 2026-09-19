"""Market data: price, shares, peers, multiples, and the S&P baseline.

Specified by docs/data-model.md "Market data".

This is the weakest data in the system (plan review error E): free providers
rate-limit, change shape and go down. Every failure must degrade to an
`unavailable` ValueObject plus a data_quality gap. A failed fetch must NEVER
fall through to an agent guessing.

TODO(roadmap Step 4, P1).
"""

from __future__ import annotations

from schema.contracts.common import ISODate, Ticker
from schema.contracts.market import CompanyProfile, MarketSnapshot, Peer


def fetch_snapshot(ticker: Ticker, as_of: ISODate) -> MarketSnapshot:
    """Price, share count and the EV bridge, all observed at ONE instant.

    Mixing a live price with a stale share count silently corrupts every
    multiple downstream, so the caller gets one timestamped object or nothing.
    """
    raise NotImplementedError("TODO(roadmap Step 4, P1)")


def fetch_profile(ticker: Ticker, as_of: ISODate) -> CompanyProfile:
    """Identity and SIC classification. SIC drives check_scope."""
    raise NotImplementedError("TODO(roadmap Step 4, P1)")


def fetch_peers(ticker: Ticker, as_of: ISODate, limit: int = 6) -> list[Peer]:
    """Comparable companies by SIC code and market-cap band.

    Deterministic where possible: peer choice moves the valuation, so it should
    not vary run to run. The Valuation Agent may override, but must say why.
    """
    raise NotImplementedError("TODO(roadmap Step 4, P1)")


def fetch_sp500_baseline(as_of: ISODate) -> dict:
    """Index forward P/E and earnings yield, plus the FRED risk-free rate."""
    raise NotImplementedError("TODO(roadmap Step 4, P1)")
