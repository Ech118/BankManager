"""Stock splits: detect the discontinuity, and adjust per-share values honestly.

THE TRAP
    A 10-K restates only the two comparative years it shows. A period that has
    already dropped out of that window when a split happens is NEVER restated,
    so a five-year series can mix pre- and post-split per-share values while
    every single number in it is correct as filed.

    NVDA, as of 2026:

        end=2022-01-30  shares= 2,535,000,000  filed=2024-02-21   <- last version
        end=2023-01-29  shares= 2,507,000,000  filed=2024-02-21
        end=2023-01-29  shares=25,070,000,000  filed=2025-02-26   <- restated 10:1

    The 10-for-1 split took effect 2024-05-31. FY2023 was restated in the FY2025
    10-K; FY2022 was not, because it was no longer shown. Diluted EPS therefore
    reads 3.85 -> 0.17 -> 1.19 across FY2022-FY2024, which looks like a collapse
    and a recovery. A five-year EPS CAGR computed from it is wrong by 10x, and
    that number would flow into the valuation and the verdict.

WHAT THIS MODULE DOES, AND DOES NOT DO
    It never silently rewrites an as-filed value. Two things happen instead:

    1. DETECT. Adjacent annual periods whose diluted share count changes by
       SPLIT_FACTOR_THRESHOLD or more, in either direction, produce a
       data_quality gap naming the boundary. This fires whether or not the
       filer tagged a ratio, so the warning is never missed.

    2. ADJUST, only when the filing itself reports the ratio. `us-gaap:
       StockholdersEquityNoteStockSplitConversionRatio1` is a reported fact with
       its own accession, so an adjusted value is arithmetic over two reported
       facts with full lineage - not an invented number. The adjusted values are
       emitted as SEPARATE metrics (`shares_diluted_split_adjusted`,
       `eps_diluted_split_adjusted`) carrying a Derivation that names the ratio
       fact and the as-filed fact. The as-filed facts are left untouched and
       stay current: no filing corrected them, so marking them superseded would
       report a restatement that never happened.

WHICH PERIODS NEED ADJUSTING
    A per-share value already reflects every split that took effect before it
    was filed. So a fact needs the cumulative ratio of the splits effective
    AFTER its own `filed_at`. NVDA's FY2022 fact was filed 2024-02-21, before
    the 2024-05-31 split, so it is multiplied by 10: 2,535M -> 25,350M, sitting
    correctly alongside FY2023's restated 25,070M. Its FY2023 fact, filed
    2025-02-26, post-dates the split and is left alone.
"""

from __future__ import annotations

from dataclasses import dataclass

from data.normalize import concept_map, derived, dimensions, periods
from data.normalize.concept_map import US_GAAP
from schema.contracts.common import ISODate, ISOTimestamp, Ticker
from schema.contracts.enums import PeriodType, SourceKind, Unit
from schema.contracts.facts import Derivation, FinancialFact

SPLIT_FACTOR_THRESHOLD = 3.0
"""Share-count ratio between adjacent years that means a split, not a buyback.

The smallest real split is 2:1 and the largest buyback or issuance in a single
year is far under 3x, so this separates them with room on both sides.
"""

SPLIT_RATIO_METRIC = "stock_split_ratio"

ADJUSTED_SUFFIX = "_split_adjusted"

PER_SHARE_ADJUSTMENT: dict[str, str] = {
    "shares_diluted": "multiply",
    "eps_diluted": "divide",
}
"""Metric -> what a 10-for-1 split does to it. Share counts multiply; anything
quoted per share divides."""

MIN_RATIO = 1.5
"""Below this a tagged "ratio" is something else - a rounding, or a ratio
expressed the other way round. Ignored rather than applied."""


@dataclass(frozen=True)
class SplitEvent:
    """One reported stock split, with the filing that reported the ratio."""

    effective_date: ISODate
    ratio: float
    accession: str | None
    filed_at: ISODate | None
    form: str | None
    concept: str


def split_events(
    companyfacts: dict, taxonomy: str = US_GAAP, as_of: ISODate | None = None
) -> list[SplitEvent]:
    """Splits the filer reported, oldest first.

    Read from EVERY form, not just 10-Ks: NVDA tagged its 10-for-1 ratio in the
    Q2 10-Q that followed the split, and never in a 10-K.
    """
    facts = (companyfacts.get("facts") or {}).get(taxonomy) or {}
    seen: dict[tuple[str, float], SplitEvent] = {}

    for concept in concept_map.candidates(SPLIT_RATIO_METRIC, taxonomy):
        node = facts.get(concept)
        if not node:
            continue
        for entries in (node.get("units") or {}).values():
            for entry in entries:
                effective, value = entry.get("end"), entry.get("val")
                filed = entry.get("filed")
                if not effective or value is None:
                    continue
                if as_of and filed and filed > as_of:
                    continue
                if not dimensions.is_consolidated(entry):
                    continue
                ratio = float(value)
                if ratio < MIN_RATIO:
                    continue
                key = (effective, ratio)
                # Keep the earliest filing that reported it: the ratio is a
                # fact about an event, repeated verbatim in later filings.
                existing = seen.get(key)
                if existing is None or (filed or "") < (existing.filed_at or ""):
                    seen[key] = SplitEvent(
                        effective_date=effective,
                        ratio=ratio,
                        accession=entry.get("accn"),
                        filed_at=filed,
                        form=entry.get("form"),
                        concept=concept,
                    )

    return _merge_duplicates(sorted(seen.values(), key=lambda e: e.effective_date))


SAME_EVENT_DAYS = 365
"""How far apart two identical ratios may be and still be ONE split.

A filer tags the same split at more than one date - announcement and effective -
and the gap is months, not days:

    NVDA   4-for-1   announced 2021-06-03, effective 2021-07-19   (46 days)
    GOOGL  20-for-1  announced 2022-02-01, effective 2022-07-15  (164 days)
    NVDA  10-for-1   tagged at 2024-05-31 and again at 2024-06-30 (30 days)

Treating those as separate events would multiply a pre-split value by 16 or by
400 - a wrong number wearing full provenance, which is worse than the
discontinuity it was meant to fix. A company does not split twice at the same
ratio inside a year, so a year is a safe window.
"""


def _merge_duplicates(events: list[SplitEvent]) -> list[SplitEvent]:
    """Collapse one split tagged at several dates into a single event.

    The LATEST date in a group wins, because that is the effective date. A
    value filed between announcement and effect is still on the old share
    basis, so using the announcement date would leave it unadjusted.
    """
    merged: list[SplitEvent] = []
    for event in events:
        previous = merged[-1] if merged else None
        if (
            previous
            and previous.ratio == event.ratio
            and _days_between(previous, event) <= SAME_EVENT_DAYS
        ):
            merged[-1] = event  # later date, same split
            continue
        merged.append(event)
    return merged


def _days_between(first: SplitEvent, second: SplitEvent) -> int:
    import datetime as dt

    return abs(
        (
            dt.date.fromisoformat(second.effective_date)
            - dt.date.fromisoformat(first.effective_date)
        ).days
    )


def cumulative_ratio(events: list[SplitEvent], filed_at: ISODate | None) -> float:
    """Product of the splits that took effect after `filed_at`.

    A value filed after a split already reflects it, so only later splits apply.
    """
    if not filed_at:
        return 1.0
    ratio = 1.0
    for event in events:
        if event.effective_date > filed_at:
            ratio *= event.ratio
    return ratio


def detect_discontinuities(
    facts: list[FinancialFact], calendar: list[periods.AnnualPeriod]
) -> list[str]:
    """data_quality gaps for share-count jumps between adjacent annual periods.

    Runs on the as-filed series and fires whether or not a ratio was tagged, so
    an untagged split still produces a warning rather than a silent 10x error.
    """
    by_period = {
        f.fiscal_period: f
        for f in facts
        if f.metric == "shares_diluted" and f.is_current and f.value
    }
    gaps: list[str] = []

    ordered = [p.label for p in calendar if p.label in by_period]
    for newer, older in zip(ordered, ordered[1:], strict=False):
        new_value = by_period[newer].value
        old_value = by_period[older].value
        if not new_value or not old_value:
            continue
        factor = new_value / old_value
        if factor < SPLIT_FACTOR_THRESHOLD and factor > 1 / SPLIT_FACTOR_THRESHOLD:
            continue
        direction = "rises" if factor >= 1 else "falls"
        gaps.append(
            f"{by_period[newer].company_id}: diluted share count {direction} "
            f"{max(factor, 1 / factor):.1f}x between {older} and {newer}. "
            f"{older} and earlier are reported on a different share basis - a "
            "stock split was never applied back to them, because no later "
            "filing showed those years. Per-share comparisons across that "
            "boundary are invalid; totals such as revenue and net income are "
            "unaffected."
        )
    return gaps


def _period_for(effective: ISODate, calendar: list[periods.AnnualPeriod]) -> str | None:
    """The fiscal period label containing a split's effective date."""
    for period in calendar:
        start = period.period_start or ""
        if start <= effective <= period.period_end:
            return period.label
    if calendar:
        newest = calendar[0]
        fiscal_year_end = newest.period_end[5:]
        return periods.label(effective, fiscal_year_end, "10-K")
    return None


def ratio_fact(
    ticker: Ticker,
    event: SplitEvent,
    period_label: str,
    *,
    cik: str | None,
    retrieved_at: ISOTimestamp,
) -> FinancialFact:
    """The reported split ratio, as a citable fact."""
    from data.normalize import to_facts

    return FinancialFact(
        fact_id=to_facts.build_fact_id(
            ticker, SPLIT_RATIO_METRIC, period_label, event.effective_date.replace("-", "")
        ),
        company_id=ticker,
        metric=SPLIT_RATIO_METRIC,
        xbrl_concept=event.concept,
        value=event.ratio,
        unit=Unit.RATIO,
        currency=None,
        scale="units",
        period_type=PeriodType.INSTANT,
        period_start=None,
        period_end=event.effective_date,
        fiscal_period=period_label,
        filing_type=to_facts.filing_type_of(event.form or "")[0],
        accession_number=event.accession,
        filed_at=event.filed_at,
        retrieved_at=retrieved_at,
        source_url=to_facts.source_url_for(cik, event.accession),
        source_location=f"{US_GAAP}:{event.concept}",
        source_kind=SourceKind.XBRL_REPORTED,
        form_raw=event.form,
        identity_key=event.effective_date,
    )


def adjusted_facts(
    ticker: Ticker,
    facts: list[FinancialFact],
    calendar: list[periods.AnnualPeriod],
    events: list[SplitEvent],
    *,
    cik: str | None,
    retrieved_at: ISOTimestamp,
) -> tuple[list[FinancialFact], list[str]]:
    """Split-adjusted per-share facts, plus the ratio facts they cite.

    Returns ([] , []) when the filer reported no ratio - the detector's warning
    stands alone rather than an adjustment being guessed.
    """
    from data.normalize import to_facts

    if not events:
        return [], []

    out: list[FinancialFact] = []
    notes: list[str] = []
    ratio_facts: dict[str, FinancialFact] = {}

    for fact in facts:
        operation = PER_SHARE_ADJUSTMENT.get(fact.metric)
        if operation is None or not fact.is_current or fact.value is None:
            continue

        applicable = [e for e in events if e.effective_date > (fact.filed_at or "")]
        if not applicable:
            continue

        ratio = cumulative_ratio(events, fact.filed_at)
        if ratio <= 1.0:
            continue

        inputs: list[FinancialFact] = []
        for event in applicable:
            key = event.effective_date
            if key not in ratio_facts:
                label = _period_for(event.effective_date, calendar) or fact.fiscal_period
                ratio_facts[key] = ratio_fact(
                    ticker, event, label, cik=cik, retrieved_at=retrieved_at
                )
            inputs.append(ratio_facts[key])

        value = fact.value * ratio if operation == "multiply" else fact.value / ratio
        symbol = "*" if operation == "multiply" else "/"
        formula = f"{fact.metric} {symbol} " + f" {symbol} ".join(
            f"{e.ratio:g}" for e in applicable
        )

        # The adjusted fact is a copy of the as-filed one, so without this it
        # would inherit the as-filed `filed_at` - a date BEFORE the split it
        # cites was public. NVDA's FY2022 value was filed 2024-02-21 and the
        # ratio months later, so a run in between would have seen a
        # split-adjusted number for a split that had not been announced.
        out.append(
            fact.model_copy(
                update={
                    "fact_id": to_facts.build_fact_id(
                        ticker, fact.metric + ADJUSTED_SUFFIX, fact.fiscal_period
                    ),
                    "metric": fact.metric + ADJUSTED_SUFFIX,
                    "value": value,
                    "source_kind": SourceKind.DERIVED,
                    "source_location": formula,
                    "derivation": Derivation(
                        formula=formula,
                        input_fact_ids=[fact.fact_id, *(f.fact_id for f in inputs)],
                        computed_by=to_facts.COMPUTED_BY,
                    ),
                    "superseded_by": None,
                    **derived.provenance([fact, *inputs]),
                }
            )
        )
        notes.append(
            f"{ticker} {fact.fiscal_period}: {fact.metric} restated to a "
            f"{ratio:g}-for-1 split basis as "
            f"{fact.metric}{ADJUSTED_SUFFIX}; the as-filed fact is unchanged."
        )

    return [*ratio_facts.values(), *out], notes
