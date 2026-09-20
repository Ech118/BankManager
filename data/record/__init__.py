"""Recorders: pull real provider responses into fixtures/real/ for offline replay.

Specified by docs/sec-pitfalls.md 6 ("pre-fetch the demo tickers so a demo never
depends on EDGAR being reachable").

Nothing in here runs during a normal run. Each module is a CLI that hits a live
provider once and writes what it got, so every test below data/tests replays a
recorded response instead of reaching the network.

  python -m data.record.companyfacts AAPL MSFT NVDA
  python -m data.record.cik_history           # audit ticker -> CIK resolution
"""
