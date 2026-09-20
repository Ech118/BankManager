"""Assemble the Factsheet: P1's deliverable, the input to everything else.

Specified by docs/data-model.md and `schema.contracts.factsheet`.
PRODUCED here, CONSUMED by calc/, audit/ and the orchestrator.

REPORTED VALUES ONLY
    Not one margin, ratio or free cash flow is computed here. Every ValueObject
    is a number a filer tagged, or a `total_debt` derived by summing disjoint
    debt buckets with a Derivation that names them. Anything else is calc/
    (ADR 0001).

EVERY NUMBER CARRIES A SOURCE, AND EVERY SOURCE RESOLVES
    `Factsheet.sources` is a registry, and its own validator rejects a citation
    that does not land in it. So each fact's accession becomes a
    `src:edgar_xbrl:<accession>` entry as the periods are built, rather than
    being reconstructed afterwards from what happened to be cited - which is how
    a registry and the values drift apart.

A PERIOD IS DATED BY ITS LAST FILING
    A period's facts can come from several filings: the original 10-K, then a
    later one that restated a line. The period's `filed_date` and `accession`
    name whichever filed LAST, the same rule derived facts follow
    (data/normalize/derived.py). Dating the period by its original 10-K while
    serving a restated value inside it would put a number in a run that predates
    the filing it came from.

MISSING IS `unavailable`, NEVER ZERO
    A metric no chain resolved becomes {"value": null, "status": "unavailable"}
    plus a data_quality gap. Zero would make margins infinite and growth rates
    negative, and would look like data (docs/sec-pitfalls.md 4).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from data.normalize import derived
from schema.contracts.common import (
    ISODate,
    ISOTimestamp,
    SourceRef,
    Ticker,
    ValueObject,
)
from schema.contracts.enums import Mode, Unit, ValueStatus, ValueType
from schema.contracts.facts import FinancialFact
from schema.contracts.factsheet import Factsheet, FinancialPeriod

PERIOD_METRICS: tuple[str, ...] = tuple(
    f
    for f in FinancialPeriod.model_fields
    if f not in {"period", "period_end", "form", "filed_date", "accession"}
)
"""Read off the contract rather than repeated here, so a new field on
FinancialPeriod cannot be silently left unfilled."""

UNITS: dict[str, Unit] = {
    "eps_diluted": Unit.USD_PER_SHARE,
    "shares_diluted": Unit.SHARES,
}
"""Everything not listed is full USD. `scale` on the underlying fact is
provenance only - `value` is already normalized (CLAUDE.md)."""

XBRL_SOURCE_PREFIX = "src:edgar_xbrl"


@dataclass
class FactsheetResult:
    factsheet: Factsheet
    gaps: list[str] = field(default_factory=list)
    sources: dict[str, SourceRef] = field(default_factory=dict)


def source_id_for(accession: str | None) -> str | None:
    """src:edgar_xbrl:<accession>, or None for a fact with no filing behind it."""
    if not accession:
        return None
    return f"{XBRL_SOURCE_PREFIX}:{accession}"


def unit_for(metric: str) -> Unit:
    return UNITS.get(metric, Unit.USD)


def _unavailable(metric: str) -> ValueObject:
    return ValueObject(
        value=None,
        unit=unit_for(metric),
        type=ValueType.FACT,
        status=ValueStatus.UNAVAILABLE,
    )


def value_of(fact: FinancialFact | None, metric: str) -> ValueObject:
    """One reported number as a ValueObject, or `unavailable`.

    A derived fact (total_debt) lists its inputs in `derived_from` so a reader
    who does not find the total in the filing can reach the lines that are.
    """
    if fact is None or fact.value is None:
        return _unavailable(metric)
    source_id = source_id_for(fact.accession_number)
    derived_from = (
        list(fact.derivation.input_fact_ids) if fact.derivation else [fact.fact_id]
    )
    if source_id is None and not derived_from:
        return _unavailable(metric)
    return ValueObject(
        value=float(fact.value),
        unit=unit_for(metric),
        type=ValueType.FACT,
        status=ValueStatus.OK,
        source_id=source_id,
        derived_from=derived_from,
    )


def source_url_for(cik: str | None, accession: str | None) -> str | None:
    if not (cik and accession):
        return None
    nodash = accession.replace("-", "")
    return (
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{nodash}/"
        f"{accession}-index.htm"
    )


def build_periods(
    facts: list[FinancialFact],
    *,
    cik: str | None,
    retrieved_at: ISOTimestamp,
) -> tuple[list[FinancialPeriod], dict[str, SourceRef], list[str]]:
    """One FinancialPeriod per fiscal year, newest first, plus their sources."""
    by_period: dict[str, dict[str, FinancialFact]] = {}
    for fact in facts:
        if not fact.is_current or not fact.fiscal_period:
            continue
        if fact.metric not in PERIOD_METRICS:
            continue
        by_period.setdefault(fact.fiscal_period, {})[fact.metric] = fact

    periods: list[FinancialPeriod] = []
    sources: dict[str, SourceRef] = {}
    gaps: list[str] = []

    for label, metrics in by_period.items():
        present = list(metrics.values())
        # The period is dated by whichever of its facts was filed last, the
        # same rule derived facts follow.
        newest = derived.last_filed(present)
        if newest is None or not newest.filed_at:
            gaps.append(
                f"{label}: no fact in this period carries a filing date, so it "
                "cannot be placed in time and was dropped."
            )
            continue

        values = {metric: value_of(metrics.get(metric), metric) for metric in PERIOD_METRICS}
        missing = sorted(m for m, v in values.items() if v.status is ValueStatus.UNAVAILABLE)
        if missing:
            gaps.append(
                f"{label}: no us-gaap concept resolved for {', '.join(missing)}. "
                "Reported as unavailable; any metric built on them is unavailable too."
            )

        for fact in present:
            source_id = source_id_for(fact.accession_number)
            if source_id and source_id not in sources:
                sources[source_id] = SourceRef(
                    kind="edgar_xbrl",
                    url=source_url_for(cik, fact.accession_number),
                    accession=fact.accession_number,
                    fetched_at=retrieved_at,
                )

        periods.append(
            FinancialPeriod(
                period=label,
                period_end=newest.period_end,
                form=newest.filing_type,
                filed_date=newest.filed_at,
                accession=newest.accession_number or "",
                **values,
            )
        )

    periods.sort(key=lambda p: p.period_end, reverse=True)
    return periods, sources, gaps


def overall_quality(gaps: list[str], periods: list[FinancialPeriod]) -> str:
    """ok | partial | degraded, as the report's banner reads it."""
    if not periods:
        return "degraded"
    if not gaps:
        return "ok"
    return "degraded" if len(gaps) > len(periods) else "partial"


def build(
    ticker: Ticker,
    *,
    as_of: ISODate,
    company_name: str,
    cik: str | None,
    facts: list[FinancialFact],
    scope,
    market,
    peers,
    baseline,
    retrieved_at: ISOTimestamp,
    gaps: list[str] | None = None,
    mode: Mode = Mode.LIVE,
    schema_version: str = "2.1.0",
) -> FactsheetResult:
    """Assemble one company's whole reported picture at one date."""
    from schema.contracts.common import DataQuality

    collected = list(gaps or [])
    periods, sources, period_gaps = build_periods(
        facts, cik=cik, retrieved_at=retrieved_at
    )
    collected.extend(period_gaps)

    if not periods:
        raise ValueError(
            f"{ticker}: no annual period could be assembled on or before {as_of}. "
            "Nothing was filed by then, or no us-gaap concept resolved."
        )

    sources.update(getattr(baseline, "sources", {}) or {})
    market_source = getattr(market, "source_id", None)
    if market_source and market_source not in sources:
        sources[market_source] = SourceRef(
            kind="market", url=None, accession=None, fetched_at=retrieved_at
        )

    factsheet = Factsheet(
        schema_version=schema_version,
        ticker=ticker,
        company_name=company_name,
        as_of=as_of,
        built_at=retrieved_at,
        mode=mode,
        scope=scope,
        data_quality=DataQuality(
            overall=overall_quality(collected, periods), gaps=collected
        ),
        market=market,
        financials=periods,
        peers=list(peers or []),
        sp500_baseline=baseline.baseline,
        consensus=None,
        # Both empty until the section parser and the news client land; the
        # contract defaults them, and an empty list is honest where a fabricated
        # entry would not be.
        filing_sections=[],
        news=[],
        sources=sources,
    )
    return FactsheetResult(factsheet=factsheet, gaps=collected, sources=sources)
