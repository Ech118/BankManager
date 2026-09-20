"""Fiscal period labelling, YTD cash-flow differencing and Q4 derivation.

Specified by docs/sec-pitfalls.md "YTD cash flow", "Q4 derivation" and
"Fiscal years are not calendar years".

Two traps live here:

1. CASH FLOW IS YEAR-TO-DATE. A 10-Q cash flow statement covers the period from
   the start of the fiscal year, not the quarter. Q3 operating cash flow is
   Q3-YTD minus Q2-YTD. Treating a YTD figure as a quarterly one overstates
   every cash metric, and the error grows through the year.

2. THERE IS NO Q4 FILING. A company files three 10-Qs and one 10-K, so Q4 must
   be derived as FY minus the nine-month YTD figure. Anything that assumes four
   quarterly filings silently loses a quarter.

Neither is reached yet: this pass normalizes ANNUAL 10-K values only. Both
functions stay unimplemented rather than half-implemented, because a wrong
quarterly number is worse than a missing one.

WHERE THE FISCAL YEAR LABEL COMES FROM
    Not the calendar month of the period end, and not `fy` on a companyfacts
    entry. `fy` is the fiscal year of the FILING, not of the fact: NVDA's period
    ending 2023-01-29 appears with fy 2023, 2024 AND 2025, because later 10-Ks
    repeat it as a comparative.

    The filer's own label is the `fy` of the EARLIEST-FILED 10-K entry for that
    period - the filing in which that year was the current year. That yields
    FY2026 for NVDA's January-2026 year end and FY2025 for WD-40's August-2025
    one, with no calendar-year guessing anywhere.

    For a period so old that its original filing predates the data (it appears
    only as a comparative), the label is walked back from the newest period by
    elapsed years, which tolerates gaps in a way that "subtract one each row"
    does not.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from dataclasses import dataclass

from schema.contracts.common import ISODate, Period

YTD_METRICS: frozenset[str] = frozenset(
    {"op_cash_flow", "capex", "sbc", "depreciation_amortization"}
)
"""Cash-flow-statement metrics reported year-to-date in a 10-Q."""

ANNUAL_FORMS: frozenset[str] = frozenset({"10-K", "10-K/A"})
"""Forms an annual value may be read from. An amendment restates its original."""

MIN_ANNUAL_DAYS = 340
MAX_ANNUAL_DAYS = 400
"""A fiscal year is 52 or 53 weeks. Anything outside this is a partial period,
a transition period, or a two-year comparative total - never an annual value."""

DAYS_PER_YEAR = 365.25


@dataclass(frozen=True)
class AnnualPeriod:
    """One fiscal year, as the filer itself numbers it."""

    label: Period
    fiscal_year: int
    period_end: ISODate
    period_start: ISODate | None

    @property
    def is_labelled_by_filer(self) -> bool:
        """False when the label was walked back rather than read from a filing."""
        return self.period_start is not None


def is_annual_duration(start: str | None, end: str) -> bool:
    """True when [start, end] spans one fiscal year."""
    if not start:
        return False
    days = (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days
    return MIN_ANNUAL_DAYS <= days <= MAX_ANNUAL_DAYS


def label(period_end: ISODate, fiscal_year_end: str, form: str) -> Period:
    """Build "FY2025" or "Q2-2026" from a period end and the filer's year end.

    A LAST-RESORT heuristic. Prefer `annual_periods()`, which reads the label
    the filer itself used. This is here for a period that never appeared as the
    current year in any filing we hold.

    The rule: a fiscal year is named for the calendar year containing most of
    it. A year ending in January or February therefore belongs to the PREVIOUS
    calendar year, which is what keeps a retailer's "FY2025" from becoming
    FY2026 because it happens to end in January.
    """
    end = dt.date.fromisoformat(period_end)
    year = end.year
    month = int((fiscal_year_end or "12-31").split("-")[0]) if fiscal_year_end else 12
    if month in (1, 2):
        year -= 1
    if form in ANNUAL_FORMS:
        return f"FY{year}"
    quarter = (end.month - 1) // 3 + 1
    return f"Q{quarter}-{year}"


def annual_periods(entries: list[dict]) -> list[AnnualPeriod]:
    """Fiscal years found in raw companyfacts entries, NEWEST FIRST.

    `entries` are raw companyfacts rows for one or more anchor concepts (see
    normalize.to_facts.ANCHOR_METRICS); only annual 10-K durations are read.
    Pass several concepts: a filer that switched revenue tags mid-history has
    the full calendar only across the union.
    """
    by_end: dict[str, list[dict]] = {}
    starts: dict[str, list[str]] = {}
    for entry in entries:
        if entry.get("form") not in ANNUAL_FORMS or entry.get("fp") != "FY":
            continue
        end, start = entry.get("end"), entry.get("start")
        if not end or not is_annual_duration(start, end):
            continue
        by_end.setdefault(end, []).append(entry)
        starts.setdefault(end, []).append(start)

    if not by_end:
        return []

    ends = sorted(by_end, reverse=True)
    years: dict[str, int] = {}
    for end in ends:
        # The filing in which this year was the CURRENT year names it.
        first_filed = min(by_end[end], key=lambda e: (e.get("filed") or "", e.get("accn") or ""))
        fiscal_year = first_filed.get("fy")
        if isinstance(fiscal_year, int):
            years[end] = fiscal_year

    years = _repair_labels(ends, years)

    out: list[AnnualPeriod] = []
    for end in ends:
        fiscal_year = years.get(end)
        if fiscal_year is None:
            continue
        common_start = Counter(s for s in starts[end] if s).most_common(1)
        out.append(
            AnnualPeriod(
                label=f"FY{fiscal_year}",
                fiscal_year=fiscal_year,
                period_end=end,
                period_start=common_start[0][0] if common_start else None,
            )
        )
    return out


def _repair_labels(ends: list[str], years: dict[str, int]) -> dict[str, int]:
    """Fix labels that are missing, duplicated, or out of order.

    A period whose original filing predates the data appears only as a
    comparative, so its earliest `fy` is a later year's. Walking back from the
    newest well-labelled period by ELAPSED YEARS - rather than subtracting one
    per row - keeps a gap in the history from shifting everything after it.
    """
    anchor_end = next((end for end in ends if end in years), None)
    if anchor_end is None:
        return years

    anchor_year = years[anchor_end]
    anchor_date = dt.date.fromisoformat(anchor_end)
    repaired = dict(years)
    seen: set[int] = set()

    for end in ends:
        elapsed = (anchor_date - dt.date.fromisoformat(end)).days
        expected = anchor_year - round(elapsed / DAYS_PER_YEAR)
        current = repaired.get(end)
        if current is None or current != expected or current in seen:
            repaired[end] = expected
        seen.add(repaired[end])
    return repaired


def ytd_to_quarterly(ytd_facts: list[dict], metric: str) -> list[dict]:
    """Difference successive YTD values into discrete quarterly ones.

    Q1 passes through unchanged; each later quarter is that quarter's YTD minus
    the previous quarter's YTD.
    """
    raise NotImplementedError(
        "TODO(P1): quarterly normalization. This pass covers annual 10-K values "
        "only; see docs/p1/STATUS.md."
    )


def derive_q4(annual: dict, nine_month_ytd: dict) -> dict:
    """Q4 = full year minus the nine-month YTD figure.

    Returns a DERIVED fact with a Derivation naming both inputs, so the verifier
    can recompute it rather than taking it on trust.
    """
    raise NotImplementedError(
        "TODO(P1): Q4 derivation. This pass covers annual 10-K values only; "
        "see docs/p1/STATUS.md."
    )
