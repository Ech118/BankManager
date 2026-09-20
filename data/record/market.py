"""Record market-provider responses into fixtures/real/<TICKER>/.

    python -m data.record.market AAPL BRK.B GOOGL NVDA WDFC

Writes `finnhub.json` per ticker: the quote, the profile, the peer list and a
slice of company news, exactly as the provider returned them. Tests install a
`RecordedMarketClient` over these files, so the market path is exercised
offline and a failure means our code changed rather than that the market moved.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

from data.ingest.market_client import (
    FinnhubClient,
    MarketClient,
    Profile,
    Quote,
)
from schema.contracts.common import ISODate, Ticker

FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "real"

NEWS_WINDOW = ("2026-08-20", "2026-09-19")
MAX_NEWS = 8


def record(ticker: str, root: Path = FIXTURES_ROOT) -> Path:
    client = FinnhubClient()
    quote = client.quote(ticker)
    profile = client.profile(ticker)
    payload = {
        "ticker": ticker,
        "quote": asdict(quote) if quote else None,
        "profile": asdict(profile) if profile else None,
        "peers": client.peers(ticker),
        "news_window": list(NEWS_WINDOW),
        "news": client.news(ticker, *NEWS_WINDOW)[:MAX_NEWS],
    }
    target = root / ticker.upper().replace(".", "-")
    target.mkdir(parents=True, exist_ok=True)
    (target / "finnhub.json").write_text(
        json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8"
    )
    print(
        f"  {ticker}: price={payload['quote']['price'] if payload['quote'] else None} "
        f"shares={payload['profile']['shares_outstanding'] if payload['profile'] else None} "
        f"peers={len(payload['peers'])} news={len(payload['news'])} -> {target}"
    )
    return target


class RecordedMarketClient(MarketClient):
    """Replays `finnhub.json`. Satisfies MarketClient, touches no network.

    An unknown ticker behaves like a provider that has never heard of it -
    None and empty lists - which is the degraded path tests need to exercise.
    """

    def __init__(self, tickers: list[str] | None = None, root: Path = FIXTURES_ROOT):
        self._root = root
        self._payloads: dict[str, dict] = {}
        for ticker in tickers or []:
            path = root / ticker.upper().replace(".", "-") / "finnhub.json"
            if path.is_file():
                self._payloads[self._key(ticker)] = json.loads(
                    path.read_text(encoding="utf-8")
                )

    @staticmethod
    def _key(ticker: str) -> str:
        return (ticker or "").upper().replace(".", "-")

    def _payload(self, ticker: Ticker) -> dict:
        return self._payloads.get(self._key(ticker), {})

    def quote(self, ticker: Ticker) -> Quote | None:
        raw = self._payload(ticker).get("quote")
        return Quote(**raw) if raw else None

    def profile(self, ticker: Ticker) -> Profile | None:
        raw = self._payload(ticker).get("profile")
        return Profile(**raw) if raw else None

    def peers(self, ticker: Ticker) -> list[str]:
        return list(self._payload(ticker).get("peers") or [])

    def news(self, ticker: Ticker, start: ISODate, end: ISODate) -> list[dict]:
        return list(self._payload(ticker).get("news") or [])


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    for ticker in argv:
        record(ticker)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
