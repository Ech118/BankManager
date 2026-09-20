"""Record everything peer selection reads, into fixtures/real/peers/<TICKER>.json.

    python -m data.record.peers NVDA AAPL KO JPM MSFT

WHY NOT RECORD THE RAW RESPONSES
    A single XBRL revenue frame is ~1MB of JSON covering every filer in the
    country, and four browse-edgar pages per industry is another 200KB. Five
    companies would put 6MB of payload in the repository to exercise a ranking
    that reads four fields from it.

    So the recorder keeps exactly the inputs `peers.select()` consumes, trimmed
    to the CIKs that industry actually contains: the candidate list, those
    candidates' revenues, their tickers, and the provider answers. The fixture
    is a few KB and replays the same decision.

WHAT THAT COSTS
    A change to the SHAPE of a browse-edgar page or a frames response will not
    be caught by these tests - only a change to the ranking will. The parsing is
    covered separately by data/tests/test_ingest.py against recorded markup.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from data.ingest import edgar_client, market_client
from data.normalize import peers as peer_rules

FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "real" / "peers"

DEFAULT_TICKERS = ("NVDA", "AAPL", "KO", "JPM", "MSFT")


def record(ticker: str, as_of: str) -> dict:
    """Fetch everything `peers.select()` would, and return it as a fixture."""
    from data import live

    data = live.load_facts(ticker, as_of)
    sic = str(data.submissions.get("sic") or "") or None
    target_revenue = live._latest_annual_revenue(data)
    period = peer_rules.frame_period(as_of)

    candidates = (
        edgar_client.fetch_sic_companies(
            sic, count=peer_rules.MAX_CANDIDATES, pages=peer_rules.CANDIDATE_PAGES
        )
        if sic
        else []
    )
    revenues = peer_rules.industry_revenues(period)
    tickers = peer_rules.primary_tickers(edgar_client.fetch_ticker_map())

    # Trim to this industry, plus the target itself.
    relevant = set(candidates) | {data.cik.zfill(10)}
    revenues = {cik: value for cik, value in revenues.items() if cik in relevant}
    tickers = {cik: tick for cik, tick in tickers.items() if cik in relevant}

    client = market_client.get_client()
    provider_peers = client.peers(ticker)

    # Market caps for everything that could plausibly be chosen, so the replay
    # never has to reach a provider.
    wanted = set(provider_peers) | set(tickers.values())
    caps: dict[str, float | None] = {}
    for candidate in sorted(wanted):
        profile = client.profile(candidate)
        cap = getattr(profile, "market_cap", None)
        if cap:
            caps[candidate] = cap

    return {
        "ticker": ticker,
        "as_of": as_of,
        "sic": sic,
        "target_cik": data.cik,
        "target_revenue": target_revenue,
        "frame_period": period,
        "candidates": candidates,
        "revenues": revenues,
        "tickers": tickers,
        "provider_peers": provider_peers,
        "market_caps": caps,
    }


def load(ticker: str) -> dict:
    """Read one recorded fixture. Tests call this; nothing here hits the network."""
    path = FIXTURES_ROOT / f"{ticker}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing. Record it with: python -m data.record.peers {ticker}"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    tickers = [t.upper() for t in argv[1:]] or list(DEFAULT_TICKERS)
    as_of = "2026-09-19"
    FIXTURES_ROOT.mkdir(parents=True, exist_ok=True)
    for ticker in tickers:
        fixture = record(ticker, as_of)
        path = FIXTURES_ROOT / f"{ticker}.json"
        path.write_text(json.dumps(fixture, indent=1, sort_keys=True), encoding="utf-8")
        print(
            f"{ticker}: SIC {fixture['sic']}, {len(fixture['candidates'])} candidates, "
            f"{len(fixture['revenues'])} with revenue -> {path.name} "
            f"({path.stat().st_size // 1024}KB)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
