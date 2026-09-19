"""Fiscal period labelling, YTD cash-flow differencing and Q4 derivation.

Specified by docs/sec-pitfalls.md "YTD cash flow" and "Q4 derivation".

Two traps live here:

1. CASH FLOW IS YEAR-TO-DATE. A 10-Q cash flow statement covers the period from
   the start of the fiscal year, not the quarter. Q3 operating cash flow is
   Q3-YTD minus Q2-YTD. Treating a YTD figure as a quarterly one overstates
   every cash metric, and the error grows through the year.

2. THERE IS NO Q4 FILING. A company files three 10-Qs and one 10-K, so Q4 must
   be derived as FY minus the nine-month YTD figure. Anything that assumes four
   quarterly filings silently loses a quarter.

TODO(roadmap Step 2, P1).
"""

from __future__ import annotations

from schema.contracts.common import ISODate, Period

YTD_METRICS: frozenset[str] = frozenset(
    {"op_cash_flow", "capex", "sbc", "depreciation_amortization"}
)
"""Cash-flow-statement metrics reported year-to-date in a 10-Q."""


def label(period_end: ISODate, fiscal_year_end: str, form: str) -> Period:
    """Build "FY2025" or "Q2-2026" from a period end and the filer's year end.

    Fiscal years rarely match calendar years, so the label comes from the
    filer's own fiscal_year_end, never from the calendar month.
    """
    raise NotImplementedError("TODO(roadmap Step 2, P1)")


def ytd_to_quarterly(ytd_facts: list[dict], metric: str) -> list[dict]:
    """Difference successive YTD values into discrete quarterly ones.

    Q1 passes through unchanged; each later quarter is that quarter's YTD minus
    the previous quarter's YTD.
    """
    raise NotImplementedError("TODO(roadmap Step 2, P1)")


def derive_q4(annual: dict, nine_month_ytd: dict) -> dict:
    """Q4 = full year minus the nine-month YTD figure.

    Returns a DERIVED fact with a Derivation naming both inputs, so the verifier
    can recompute it rather than taking it on trust.
    """
    raise NotImplementedError("TODO(roadmap Step 2, P1)")
