"""Record a built Factsheet into fixtures/real/<TICKER>/factsheet.json.

    python -m data.record.factsheet AAPL JPM NVDA KO MSFT

WHY RECORD THE OUTPUT AND NOT ONLY THE INPUTS
    The other recorders capture what SEC returned, so the normalization can be
    re-run against it. This one captures what P1 SHIPPED, which is a different
    thing and answers a different question: not "did we parse this correctly"
    but "did the object other partitions consume change shape".

    It is the closest thing P1 has to a contract test against real companies. A
    diff here is either a deliberate improvement or a regression in something
    calc/ and audit/ are reading, and either way somebody should look.

WHAT IS IN IT
    A full Factsheet, including a live price and a market cap observed at the
    moment of recording. Those move; the tests that read these fixtures assert
    STRUCTURE, provenance and internal consistency, never a specific price.

MARKET CAPS AT RECORDING TIME
    AAPL $4,905.5B · MSFT $3,666.6B · NVDA $5,356.7B · KO $379.7B · JPM $929.5B
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "real"

DEFAULT_TICKERS = ("AAPL", "JPM", "NVDA", "KO", "MSFT")

AS_OF = "2026-09-19"


def load(ticker: str) -> dict:
    """Read one recorded factsheet. Tests call this; it never hits the network."""
    path = FIXTURES_ROOT / ticker / "factsheet.json"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing. Record it with: "
            f"MODE=live python -m data.record.factsheet {ticker}"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def record(ticker: str, as_of: str) -> dict:
    from data import live

    return live.build_factsheet(ticker, as_of)


def main(argv: list[str]) -> int:
    import os

    if os.environ.get("MODE", "mock").lower() != "live":
        print("Set MODE=live: this recorder fetches from SEC and the market provider.")
        return 2

    tickers = [t.upper() for t in argv[1:]] or list(DEFAULT_TICKERS)
    for ticker in tickers:
        factsheet = record(ticker, AS_OF)
        directory = FIXTURES_ROOT / ticker
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "factsheet.json"
        path.write_text(
            json.dumps(factsheet, indent=1, sort_keys=True), encoding="utf-8"
        )
        cap = factsheet["market"].get("market_cap", {}).get("value")
        print(
            f"{ticker}: {len(factsheet['financials'])} periods, "
            f"{len(factsheet['peers'])} peers, "
            f"market cap {cap / 1e9:,.1f}B, "
            f"quality {factsheet['data_quality']['overall']} "
            f"({len(factsheet['data_quality']['gaps'])} gaps) "
            f"-> {path.relative_to(FIXTURES_ROOT.parent.parent)} "
            f"({path.stat().st_size // 1024}KB)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
