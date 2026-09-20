"""Trailing-twelve-month flow facts, from the latest 10-Q.

Asked for by P2 in docs/requests/2026-09-20-p2-to-p1-calculate-valuation-wrapper.md:
without a TTM figure, every multiple calc/ publishes divides the latest FULL
fiscal year, so when a year is partly elapsed our P/E reads higher than the one
on a reader's screen. That is defensible and it still loses the reader.

THE ARITHMETIC
    TTM = latest full fiscal year + current year-to-date - prior-year
    year-to-date

    Both year-to-date figures come from the SAME 10-Q: the current one, and the
    comparative the filer prints beside it. Taking the prior-year figure from
    the prior year's own 10-Q instead would mix two filings and, worse, miss
    that a filer restates its comparative - the comparative in THIS filing is
    what this filing's arithmetic is consistent with.

WHY NOT SUM FOUR QUARTERS
    Identical result, more ways to be wrong. A 10-Q reports both a quarterly and
    a year-to-date duration for most concepts; picking the wrong one silently
    scales a number by three (docs/sec-pitfalls.md 2). Two YTD figures and one
    annual figure is three reads instead of four, and each is a period the filer
    actually labelled.

WHEN THE LATEST FILING IS THE 10-K
    TTM is the fiscal year, exactly. No arithmetic, and the derived fact records
    that it has one input rather than three, so nobody reading the lineage
    wonders where the quarters went.

    The test is whether the fiscal year already ENDS AFTER the quarter, not
    which document arrived last. Microsoft's FY2026 10-K (year ended 2026-06-30)
    was filed 2026-07-29, after its Q3 10-Q (quarter ended 2026-03-31). Adding
    that quarter's year-to-date to a year that already contains it counts nine
    months twice: capex came out at $148.6B against a full-year $115.9B. A
    filer whose 10-K lands before its next 10-Q is the ordinary state of affairs
    for four months of every year, so this is not an edge case.

MISSING INPUTS
    If any of the three is absent, the TTM fact is `unavailable` with a gap
    naming what was missing. Never a partial sum: a TTM built from two of three
    inputs is not a smaller number, it is a wrong one.

EPS IS SUMMED, WHICH IS CONVENTIONAL AND SLIGHTLY LOSSY
    Per-share figures do not add exactly - each quarter divides by its own share
    count, and buybacks move it. Every data provider sums them anyway, and the
    alternative (TTM net income over TTM shares) disagrees with the published
    figure a reader is checking against. The derivation records the sum, so a
    verifier recomputes what we actually did.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from data.normalize import concept_map, dimensions
from data.normalize.concept_map import US_GAAP
from schema.contracts.common import ISODate, ISOTimestamp, Ticker
from schema.contracts.enums import PeriodType, SourceKind, Unit
from schema.contracts.facts import FinancialFact

TTM_METRICS: tuple[str, ...] = (
    "revenue",
    "gross_profit",
    "operating_income",
    "net_income",
    "eps_diluted",
    "op_cash_flow",
    "capex",
    "sbc",
)
"""Flow metrics only. A balance-sheet figure has no trailing twelve months -
cash is cash on a date - and offering `cash_ttm` would invite someone to use it."""

TTM_SUFFIX = "_ttm"
YTD_SUFFIX = "_ytd"

QUARTERLY_FORMS: frozenset[str] = frozenset({"10-Q", "10-Q/A"})

YEAR_DAYS = 365
YEAR_TOLERANCE_DAYS = 25
"""How far from exactly a year apart the comparative may sit. Fiscal quarters
end on a weekday, so the same quarter one year earlier lands within a week or
two; 25 days allows a 52/53-week filer's extra week without ever reaching the
neighbouring quarter, which is 90 days away."""

DURATION_TOLERANCE_DAYS = 20
"""The comparative must cover the same span as the current figure. Nine months
against six is the error this exists to catch."""


@dataclass
class TtmResult:
    facts: list[FinancialFact] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Entry:
    """One companyfacts row, with the fields this module reads."""

    concept: str
    unit: str
    value: float
    start: ISODate
    end: ISODate
    accession: str
    filed: ISODate
    form: str
    fiscal_year: int | None
    fiscal_period: str | None

    @property
    def days(self) -> int:
        return (dt.date.fromisoformat(self.end) - dt.date.fromisoformat(self.start)).days


def _entries(
    companyfacts: dict, concept: str, taxonomy: str, as_of: ISODate | None
) -> list[Entry]:
    """Consolidated 10-Q duration rows for one concept, filed on or before as_of."""
    node = (companyfacts.get("facts") or {}).get(taxonomy, {}).get(concept)
    if not node:
        return []

    out: list[Entry] = []
    for unit, rows in (node.get("units") or {}).items():
        for row in rows:
            if row.get("form") not in QUARTERLY_FORMS:
                continue
            if not dimensions.is_consolidated(row):
                continue
            start, end, filed = row.get("start"), row.get("end"), row.get("filed")
            if not (start and end and filed and row.get("accn")):
                continue
            if as_of and filed > as_of:
                continue
            out.append(
                Entry(
                    concept=concept,
                    unit=unit,
                    value=float(row["val"]),
                    start=start,
                    end=end,
                    accession=row["accn"],
                    filed=filed,
                    form=row["form"],
                    fiscal_year=row.get("fy"),
                    fiscal_period=row.get("fp"),
                )
            )
    return out


def latest_quarter(
    companyfacts: dict, *, taxonomy: str = US_GAAP, as_of: ISODate | None = None
) -> tuple[str, ISODate, ISODate] | None:
    """(accession, filed_at, period_end) of the newest 10-Q filed by `as_of`.

    Scans the TTM concepts rather than the submissions index because a filing
    that reported none of them is of no use here, and companyfacts is already in
    memory.
    """
    newest: Entry | None = None
    for metric in TTM_METRICS:
        for concept in concept_map.candidates(metric, taxonomy):
            for entry in _entries(companyfacts, concept, taxonomy, as_of):
                key = (entry.filed, entry.accession, entry.end)
                if newest is None or key > (newest.filed, newest.accession, newest.end):
                    newest = entry
    if newest is None:
        return None
    # The quarter this filing covers is its latest period end, not this row's.
    same_filing = [
        e
        for metric in TTM_METRICS
        for concept in concept_map.candidates(metric, taxonomy)
        for e in _entries(companyfacts, concept, taxonomy, as_of)
        if e.accession == newest.accession
    ]
    period_end = max(e.end for e in same_filing)
    return newest.accession, newest.filed, period_end


def _ytd_pair(
    entries: list[Entry], accession: str, period_end: ISODate
) -> tuple[Entry, Entry] | None:
    """The current year-to-date row and its prior-year comparative.

    Both must come from `accession`, cover the same span, and end a year apart.
    """
    in_filing = [e for e in entries if e.accession == accession]
    current = [e for e in in_filing if e.end == period_end]
    if not current:
        return None
    # The longest duration ending at the quarter end is the year-to-date figure;
    # the short one is the quarter alone (docs/sec-pitfalls.md 2).
    cur = max(current, key=lambda e: e.days)

    end_date = dt.date.fromisoformat(cur.end)
    comparatives = [
        e
        for e in in_filing
        if e is not cur
        and abs((end_date - dt.date.fromisoformat(e.end)).days - YEAR_DAYS)
        <= YEAR_TOLERANCE_DAYS
        and abs(e.days - cur.days) <= DURATION_TOLERANCE_DAYS
    ]
    if not comparatives:
        return None
    prior = max(comparatives, key=lambda e: e.days)
    return cur, prior


def quarter_label(
    period_end: ISODate, fiscal_period: str | None, fiscal_year: int | None
) -> str:
    """`Q3-2026`, from the filer's own numbering where it gives one."""
    if fiscal_period and fiscal_period.startswith("Q") and fiscal_year:
        return f"{fiscal_period}-{fiscal_year}"
    return f"Q1-{period_end[:4]}"


def prior_year_label(current: str) -> str:
    """The same quarter, one year earlier.

    Not read from the comparative row's own `fy`: on a companyfacts entry `fy`
    is the FILING's fiscal year, so a 10-Q's prior-year comparative carries the
    CURRENT year and both rows would be labelled Q3-2026 - one overwriting the
    other's fact_id. Same trap as the annual labels (STATUS.md finding 2).
    """
    quarter, _, year = current.partition("-")
    return f"{quarter}-{int(year) - 1}" if year.isdigit() else current


def _unit_for(metric: str, raw_unit: str) -> Unit:
    if metric == "eps_diluted":
        return Unit.USD_PER_SHARE
    if raw_unit.lower() in {"usd"}:
        return Unit.USD
    return Unit.USD


def _ytd_fact(
    ticker: Ticker,
    metric: str,
    entry: Entry,
    label: str,
    *,
    cik: str | None,
    retrieved_at: ISOTimestamp,
) -> FinancialFact:
    """One year-to-date figure as a citable fact.

    These exist so the TTM fact's `input_fact_ids` resolve. A derived fact whose
    inputs cannot be looked up gives the verifier a dead link, which is worse
    than no lineage at all because it looks like lineage.
    """
    from data.normalize import to_facts

    value = entry.value
    if metric in concept_map.SIGN_FLIPPED and value < 0:
        value = -value
    return FinancialFact(
        fact_id=to_facts.build_fact_id(ticker, metric + YTD_SUFFIX, label),
        company_id=ticker,
        metric=metric + YTD_SUFFIX,
        xbrl_concept=entry.concept,
        value=value,
        unit=_unit_for(metric, entry.unit),
        currency="USD",
        scale="units",
        period_type=PeriodType.DURATION,
        period_start=entry.start,
        period_end=entry.end,
        fiscal_period=label,
        filing_type=to_facts.filing_type_of(entry.form)[0],
        accession_number=entry.accession,
        filed_at=entry.filed,
        retrieved_at=retrieved_at,
        source_url=to_facts.source_url_for(cik, entry.accession),
        source_location=f"{US_GAAP}:{entry.concept}",
        source_kind=SourceKind.XBRL_REPORTED,
        form_raw=entry.form,
    )


def _annual_fact(facts: list[FinancialFact], metric: str) -> FinancialFact | None:
    """The newest current full-year fact for one metric."""
    annual = [
        f
        for f in facts
        if f.metric == metric
        and f.is_current
        and f.value is not None
        and (f.fiscal_period or "").startswith("FY")
    ]
    return max(annual, key=lambda f: f.period_end) if annual else None


def build(
    ticker: Ticker,
    companyfacts: dict,
    annual_facts: list[FinancialFact],
    *,
    as_of: ISODate | None = None,
    taxonomy: str = US_GAAP,
    cik: str | None = None,
    retrieved_at: ISOTimestamp | None = None,
) -> TtmResult:
    """TTM facts for every flow metric, plus the year-to-date facts they cite."""
    from data.normalize import to_facts

    retrieved_at = retrieved_at or to_facts.utc_now()
    result = TtmResult()

    quarter = latest_quarter(companyfacts, taxonomy=taxonomy, as_of=as_of)

    for metric in TTM_METRICS:
        annual = _annual_fact(annual_facts, metric)
        if annual is None:
            result.gaps.append(
                f"{ticker}: no full-year {metric}, so {metric}{TTM_SUFFIX} is "
                "unavailable. A trailing figure needs a year to start from."
            )
            continue

        # A fiscal year that already ends after the quarter CONTAINS it, so the
        # trailing twelve months are that year and adding the quarter's
        # year-to-date would count part of the year twice.
        superseded = quarter is not None and annual.period_end >= quarter[2]

        if quarter is None or superseded:
            # No 10-Q since the 10-K: the trailing twelve months ARE the year.
            why = (
                "no 10-Q filed since"
                if quarter is None
                else f"the fiscal year ends {annual.period_end}, after the "
                f"latest 10-Q's quarter ending {quarter[2]}"
            )
            result.facts.append(
                to_facts.derive_fact(
                    metric + TTM_SUFFIX,
                    f"{annual.fiscal_period} {metric} (latest full year; {why})",
                    [annual],
                    float(annual.value),
                )
            )
            continue

        accession, filed_at, period_end = quarter
        pair = None
        for concept in concept_map.candidates(metric, taxonomy):
            entries = _entries(companyfacts, concept, taxonomy, as_of)
            pair = _ytd_pair(entries, accession, period_end)
            if pair:
                break

        if pair is None:
            result.gaps.append(
                f"{ticker}: the 10-Q {accession} carries no year-to-date {metric} "
                f"with a prior-year comparative, so {metric}{TTM_SUFFIX} is "
                "unavailable rather than a partial sum."
            )
            continue

        cur, prior = pair
        label = quarter_label(cur.end, cur.fiscal_period, cur.fiscal_year)
        prior_label = prior_year_label(label)

        cur_fact = _ytd_fact(
            ticker, metric, cur, label, cik=cik, retrieved_at=retrieved_at
        )
        prior_fact = _ytd_fact(
            ticker, metric, prior, prior_label, cik=cik, retrieved_at=retrieved_at
        )
        value = float(annual.value) + cur_fact.value - prior_fact.value

        ttm = to_facts.derive_fact(
            metric + TTM_SUFFIX,
            f"{annual.fiscal_period} {metric} + {label} year-to-date "
            f"- {prior_label} year-to-date",
            [annual, cur_fact, prior_fact],
            value,
        )
        # derive_fact dates a derived fact by its newest input, which for a TTM
        # is always the 10-Q. Stated rather than assumed, because the whole fact
        # only became knowable when that filing landed.
        ttm = ttm.model_copy(
            update={
                "filed_at": filed_at,
                "accession_number": accession,
                "period_start": prior.end,
                "period_end": cur.end,
                "period_type": PeriodType.DURATION,
                "fiscal_period": label,
            }
        )
        result.facts.extend([cur_fact, prior_fact, ttm])

    return result
