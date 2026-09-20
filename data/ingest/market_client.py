"""Market data: price, company profile, peers and news, behind one interface.

Specified by docs/data-model.md "Market data".

This is the weakest data in the system (plan review error E): free providers
rate-limit, change shape and go down. Every failure must degrade to an
`unavailable` ValueObject plus a data_quality gap. A failed fetch must NEVER
fall through to an agent guessing.

THE INTERFACE EXISTS SO THE PROVIDER CAN BE SWAPPED
    `MarketClient` is a Protocol with four methods. `FinnhubClient` implements
    it against Finnhub's free tier, which was verified to serve /quote,
    /stock/profile2, /stock/peers and /company-news without a paid plan.
    Swapping in another vendor means writing one class, not touching the
    snapshot, the peer ranking or the MCP tools.

    `set_client()` installs a replacement, which is how tests replay recorded
    responses without touching the network - the same pattern as
    data/ingest/edgar_client.py.

PRICES ARE NOT IMMUTABLE
    A filing is cached forever under its accession; a quote is cached for
    QUOTE_TTL_SECONDS and carries the instant it was observed. Combining a live
    price with a stale share count corrupts market cap and every multiple built
    on it, so MarketSnapshot timestamps the whole bundle rather than each field
    (docs/sec-pitfalls.md 8).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import httpx

from data.ingest import cache, env
from schema.contracts.common import ISODate, Ticker

FINNHUB_BASE = "https://finnhub.io/api/v1"

QUOTE_TTL_SECONDS = 300
"""Five minutes. Long enough to survive a run, short enough that a demo shows
a price someone can recognise."""

PROFILE_TTL_SECONDS = cache.DAY_SECONDS
PEERS_TTL_SECONDS = cache.DAY_SECONDS
NEWS_TTL_SECONDS = 3600

_client: MarketClient | None = None


@dataclass(frozen=True)
class Quote:
    """One observed price, with the instant it was observed at."""

    ticker: str
    price: float
    observed_at: int
    previous_close: float | None = None
    currency: str = "USD"
    source: str = "finnhub"


@dataclass(frozen=True)
class Profile:
    """Provider-side company identity. SEC is authoritative; this fills gaps."""

    ticker: str
    name: str | None = None
    exchange: str | None = None
    currency: str = "USD"
    shares_outstanding: float | None = None
    market_cap: float | None = None
    industry: str | None = None
    source: str = "finnhub"


@runtime_checkable
class MarketClient(Protocol):
    """Everything the data layer needs from a price provider."""

    def quote(self, ticker: Ticker) -> Quote | None:
        """Latest price, or None when the provider failed or knows no such symbol."""
        ...

    def profile(self, ticker: Ticker) -> Profile | None:
        """Identity, share count and market cap as the provider sees them."""
        ...

    def peers(self, ticker: Ticker) -> list[str]:
        """Provider-chosen comparable tickers. Empty list on any failure."""
        ...

    def news(self, ticker: Ticker, start: ISODate, end: ISODate) -> list[dict]:
        """Company news in [start, end]. Empty list on any failure."""
        ...


class FinnhubClient:
    """Finnhub free tier. Every method returns a neutral value on failure.

    NOT raising is the point: a provider outage must become an `unavailable`
    field plus a data_quality gap, never an exception that aborts a run
    (docs/mcp-tools.md, error conventions).
    """

    def __init__(self, api_key: str | None = None, http: httpx.Client | None = None):
        self._api_key = api_key
        self._http = http

    # -- plumbing ----------------------------------------------------------
    def _key(self) -> str:
        if self._api_key is None:
            self._api_key = env.require(
                "FINNHUB_API_KEY", hint="Get a free key at https://finnhub.io."
            )
        return self._api_key

    def _session(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(timeout=15.0, follow_redirects=True)
        return self._http

    @staticmethod
    def symbol(ticker: Ticker) -> str:
        """Finnhub spells share classes with a dot: BRK-B is BRK.B."""
        return (ticker or "").strip().upper().replace("-", ".")

    def _get(self, path: str, params: dict[str, Any], cache_key: str, ttl: float) -> Any:
        """Cached GET. Returns None on any failure, having swallowed it."""
        hit = cache.get_fresh(cache_key, ttl)
        if hit is not None:
            try:
                return json.loads(hit)
            except ValueError:
                pass
        try:
            response = self._session().get(
                f"{FINNHUB_BASE}{path}", params={**params, "token": self._key()}
            )
            if response.status_code != 200:
                return None
            payload = response.json()
        except Exception:
            return None
        cache.put(cache_key, json.dumps(payload).encode("utf-8"))
        return payload

    # -- the interface -----------------------------------------------------
    def quote(self, ticker: Ticker) -> Quote | None:
        symbol = self.symbol(ticker)
        payload = self._get(
            "/quote", {"symbol": symbol}, f"finnhub/quote/{symbol}.json", QUOTE_TTL_SECONDS
        )
        if not isinstance(payload, dict):
            return None
        price = payload.get("c")
        # Finnhub answers an unknown symbol with a 200 and every field zero.
        if not price:
            return None
        return Quote(
            ticker=ticker,
            price=float(price),
            observed_at=int(payload.get("t") or time.time()),
            previous_close=float(payload["pc"]) if payload.get("pc") else None,
        )

    def profile(self, ticker: Ticker) -> Profile | None:
        symbol = self.symbol(ticker)
        payload = self._get(
            "/stock/profile2",
            {"symbol": symbol},
            f"finnhub/profile/{symbol}.json",
            PROFILE_TTL_SECONDS,
        )
        if not isinstance(payload, dict) or not payload:
            return None
        shares = payload.get("shareOutstanding")
        cap = payload.get("marketCapitalization")
        return Profile(
            ticker=ticker,
            name=payload.get("name"),
            exchange=payload.get("exchange"),
            currency=payload.get("currency") or "USD",
            # Both are quoted in MILLIONS.
            shares_outstanding=float(shares) * 1e6 if shares else None,
            market_cap=float(cap) * 1e6 if cap else None,
            industry=payload.get("finnhubIndustry"),
        )

    def peers(self, ticker: Ticker) -> list[str]:
        symbol = self.symbol(ticker)
        payload = self._get(
            "/stock/peers", {"symbol": symbol}, f"finnhub/peers/{symbol}.json", PEERS_TTL_SECONDS
        )
        if not isinstance(payload, list):
            return []
        return [str(p) for p in payload if p and str(p).upper() != symbol]

    def news(self, ticker: Ticker, start: ISODate, end: ISODate) -> list[dict]:
        symbol = self.symbol(ticker)
        payload = self._get(
            "/company-news",
            {"symbol": symbol, "from": start, "to": end},
            f"finnhub/news/{symbol}/{start}_{end}.json",
            NEWS_TTL_SECONDS,
        )
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]


class NullMarketClient:
    """A provider that is always down. What mock mode and a missing key get.

    Exists so the degraded path is the DEFAULT rather than an error branch
    nobody exercises: with this installed, a snapshot still builds and simply
    reports price unavailable.
    """

    def quote(self, ticker: Ticker) -> Quote | None:
        return None

    def profile(self, ticker: Ticker) -> Profile | None:
        return None

    def peers(self, ticker: Ticker) -> list[str]:
        return []

    def news(self, ticker: Ticker, start: ISODate, end: ISODate) -> list[dict]:
        return []


def set_client(client: MarketClient | None) -> None:
    """Install a client (tests) or reset to the default one (None)."""
    global _client
    _client = client


def get_client() -> MarketClient:
    """The installed client, or a Finnhub one when a key is configured."""
    global _client
    if _client is None:
        try:
            env.require("FINNHUB_API_KEY")
        except RuntimeError:
            return NullMarketClient()
        _client = FinnhubClient()
    return _client
