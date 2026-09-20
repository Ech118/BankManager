"""Audit ticker -> CIK resolution for the largest US companies.

    python -m data.record.cik_history            # the built-in list
    python -m data.record.cik_history AAPL MSFT  # specific tickers

Reports every ticker whose resolved CIK holds fewer than two annual 10-K
periods of XBRL data. Those are the ones that need a row in
data/ingest/ticker_overrides.py, because SEC's ticker map points at the CURRENT
registrant: after a holding-company reorganisation the ticker moves to a CIK
with no filing history while the 10-Ks stay under the predecessor.

Hits EDGAR once per ticker at 8 req/s. Not part of any test run.
"""

from __future__ import annotations

import sys

from data.ingest import companyfacts as companyfacts_api
from data.ingest import edgar_client
from data.ingest.ticker_overrides import override_for
from data.normalize import scope

LARGEST_US_COMPANIES: tuple[str, ...] = (
    "NVDA", "MSFT", "AAPL", "GOOGL", "AMZN", "META", "AVGO", "TSLA", "BRK-B", "JPM",
    "WMT", "ORCL", "LLY", "V", "NFLX", "MA", "XOM", "COST", "JNJ", "HD",
    "PG", "PLTR", "BAC", "ABBV", "CVX", "KO", "AMD", "GE", "CSCO", "TMUS",
    "WFC", "CRM", "PM", "IBM", "UNH", "MS", "ABT", "AXP", "MCD", "GS",
    "DIS", "MRK", "NOW", "RTX", "CAT", "T", "PEP", "INTU", "VZ", "UBER",
    "BKNG", "QCOM", "TXN", "BLK", "AMGN", "SCHW", "C", "SPGI", "BSX", "ISRG",
    "ADBE", "NEE", "TMO", "SYK", "PGR", "HON", "ETN", "DHR", "LOW", "GILD",
    "PFE", "TJX", "UNP", "CMCSA", "ANET", "COP", "ADP", "MU", "VRTX", "LRCX",
    "KLAC", "PANW", "BX", "MDT", "APH", "CB", "ADI", "SBUX", "MRSH", "PLD",
    "LMT", "BMY", "CRWD", "INTC", "DE", "SO", "ICE", "MO", "AMT", "NKE",
)
"""Roughly the 100 largest US-listed companies by market cap, September 2026.

MMC is spelled MRSH here: Marsh & McLennan changed ticker, and SEC's map had
already followed. The old spelling resolves to nothing, which check_scope
reports as "not in company_tickers.json ... may be delisted" - the right answer,
and not a case for an override."""


def audit(tickers: list[str]) -> list[dict]:
    """Resolve each ticker and count its annual 10-K periods."""
    rows: list[dict] = []
    for ticker in tickers:
        override = override_for(ticker)
        row: dict = {"ticker": ticker, "override": bool(override)}
        try:
            cik = edgar_client.lookup_cik(ticker)
        except KeyError as exc:
            rows.append({**row, "cik": None, "periods": 0, "note": str(exc)[:90]})
            continue

        row["cik"] = cik
        try:
            facts = companyfacts_api.fetch_companyfacts(cik)
        except Exception as exc:
            rows.append({**row, "periods": 0, "note": f"companyfacts failed: {exc}"[:90]})
            continue

        row["periods"] = scope.annual_period_count(facts)
        row["name"] = facts.get("entityName")
        row["taxonomies"] = sorted((facts.get("facts") or {}).keys())
        rows.append(row)
    return rows


def main(argv: list[str]) -> int:
    tickers = argv or list(LARGEST_US_COMPANIES)
    rows = audit(tickers)

    suspect = [r for r in rows if r.get("periods", 0) < scope.MIN_ANNUAL_FILINGS]
    foreign = [r for r in rows if "us-gaap" not in (r.get("taxonomies") or ["us-gaap"])]

    print(f"\nchecked {len(rows)} tickers")
    print(f"{len(rows) - len(suspect)} resolve to a CIK with >= "
          f"{scope.MIN_ANNUAL_FILINGS} annual 10-K periods\n")

    if suspect:
        print("NEEDS AN OVERRIDE (fewer than 2 annual 10-K periods):")
        for row in suspect:
            marker = " [override already applied]" if row["override"] else ""
            print(f"  {row['ticker']:6} cik={row.get('cik')} periods={row.get('periods')} "
                  f"{row.get('name') or ''}{marker}")
            if row.get("note"):
                print(f"         {row['note']}")
    else:
        print("No ticker needs an override.")

    if foreign:
        print("\nNO us-gaap TAXONOMY (foreign private issuer, scope=partial):")
        for row in foreign:
            print(f"  {row['ticker']:6} cik={row.get('cik')} "
                  f"taxonomies={','.join(row.get('taxonomies') or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
