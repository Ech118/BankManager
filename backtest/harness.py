"""Run the pipeline over historical dates and collect the predictions.

Specified by docs/roadmap.md Step 6.

Calls orchestrator.api.run_analysis with an `as_of` and the anonymizer from
anonymize.py. The harness never touches data/ or calc/ directly: it goes through
the same entry point a live run uses, so a backtest exercises the real pipeline
rather than a parallel one that might diverge.

TODO(roadmap Step 6, P2).
"""

from __future__ import annotations

from schema.contracts.common import ISODate, Ticker


def run_one(ticker: Ticker, as_of: ISODate, anonymize: bool = True) -> dict:
    """One historical run. Returns the verdict plus the run metadata."""
    raise NotImplementedError("TODO(roadmap Step 6, P2)")


def run_many(tickers: list[Ticker], as_of: ISODate, anonymize: bool = True) -> list[dict]:
    """A cohort at one cutoff date.

    Bulk runs use the SHORT horizon only: a five-year horizon needs five years of
    outcomes, which limits the sample to companies that existed then and
    survived, and survivorship bias would flatter every result.
    """
    raise NotImplementedError("TODO(roadmap Step 6, P2)")
