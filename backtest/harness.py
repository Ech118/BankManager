"""Backtest harness (plan.txt 15.14 P2 step 7: "harness that calls
orchestrator.run_analysis with as_of and redact"). Calls other partitions
ONLY through their api.py (plan.txt 15.8): data.api for the point-in-time
factsheet (needed to build the anonymizer) and orchestrator.api for the
actual run.
"""
from __future__ import annotations

from typing import Optional

from backtest.anonymize import build_redactor
from backtest.grade import grade_case


def run_case(
    ticker: str,
    as_of: str,
    realized_annualized_return: float,
    sp500_realized_return: Optional[float] = None,
) -> dict:
    """Run one point-in-time backtest case end to end and grade it.

    Returns a dict with either the graded result or an "error" key (never
    raises) so a bad case does not abort a larger batch (plan.txt 14.A: "The
    demo must state which method was used" - callers should surface errors,
    not swallow them silently).
    """
    from data import api as data_api
    from orchestrator import api as orch_api

    try:
        factsheet = data_api.build_factsheet(ticker, as_of=as_of)
    except ValueError as exc:
        return {"ticker": ticker, "as_of": as_of, "error": f"build_factsheet: {exc}"}

    redact = build_redactor(factsheet["company_name"], factsheet["ticker"], as_of)

    try:
        verdict = orch_api.run_analysis(ticker, as_of=as_of, redact=redact)
    except (ValueError, NotImplementedError) as exc:
        return {"ticker": ticker, "as_of": as_of, "error": f"run_analysis: {exc}"}

    graded = grade_case(ticker, as_of, verdict, realized_annualized_return, sp500_realized_return)
    if verdict.get("mode") != "backtest":
        # The orchestrator did not honour as_of/redact (e.g. P3's mock stub
        # ignores both, plan.txt Phase 1). The point-in-time guarantee
        # (error A) is NOT verified for this case - flag it rather than
        # silently presenting it as a clean point-in-time result.
        graded["point_in_time_verified"] = False
        graded["warning"] = f"orchestrator did not run in backtest mode (mode={verdict.get('mode')!r})"
    else:
        graded["point_in_time_verified"] = True
    return graded


def run_backtest(cases: list[dict]) -> list[dict]:
    """cases: [{"ticker", "as_of", "realized_annualized_return",
    "sp500_realized_return" (optional)}, ...]. Returns one result per case."""
    results = []
    for case in cases:
        results.append(run_case(
            case["ticker"],
            case["as_of"],
            case["realized_annualized_return"],
            case.get("sp500_realized_return"),
        ))
    return results
