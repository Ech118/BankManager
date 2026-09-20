"""Assemble FinancialFact rows from normalized XBRL payloads.

Specified by docs/data-model.md "From payload to fact".

The single place a FinancialFact is constructed from provider data, so the
provenance rules cannot be bypassed: every row gets its accession, filing date,
retrieval timestamp and the XBRL concept that actually matched.

Values are normalized to FULL UNITS here. `scale` records what the filing said
("millions") purely as provenance; no consumer ever multiplies by it again.
`companyfacts` already reports full units, so `scale` is "units" throughout.

THIS PASS IS ANNUAL ONLY
    Five fiscal years of 10-K values. Quarterly normalization needs YTD
    differencing and Q4 derivation (normalize/periods.py), which are not built.

A MISSING METRIC HAS NO ROW
    The truth layer holds only numbers that exist. A metric that resolves to
    nothing produces a `gap` string instead of a fact, and build_factsheet turns
    that into {"value": null, "status": "unavailable"} - which is where the
    contract puts missing data, since a ValueObject has a `status` and a
    FinancialFact does not. It is never 0, and the gap is never silent.

TOTAL DEBT IS A DERIVED FACT
    Most filers report no single total-debt line, so the total is a sum. Every
    component is emitted as its own `xbrl_reported` fact and the total carries a
    Derivation naming them, so a reader who does not find the total in the
    filing can follow it to the lines that are in there.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from data.normalize import concept_map, dimensions, periods, restatements, splits
from data.normalize.concept_map import US_GAAP
from schema.contracts.common import ISODate, ISOTimestamp, Ticker
from schema.contracts.enums import FilingType, PeriodType, SourceKind, Unit
from schema.contracts.facts import Derivation, FinancialFact

ANCHOR_METRICS: tuple[str, ...] = ("revenue", "net_income")
"""Metrics whose entries define the fiscal calendar. Two, because a filer that
switched revenue tags mid-history has a complete calendar only across both."""

COMPUTED_BY = "data.normalize"
"""Who summed a derived fact here. NOT calc/: this is tag normalization, and
calc/ owns the valuation math (ADR 0001)."""

DEBT_COMPONENT_METRIC = "total_debt_component"
"""Metric name for one reported line inside a summed total debt. Kept distinct
from `total_debt` so a consumer asking for total debt gets one row, not four."""

UNIT_BY_XBRL: dict[str, Unit] = {
    "USD": Unit.USD,
    "USD/shares": Unit.USD_PER_SHARE,
    "shares": Unit.SHARES,
    "pure": Unit.RATIO,
}

FILING_INDEX_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{nodash}/{accession}-index.htm"


@dataclass
class NormalizedFacts:
    """Everything one companyfacts payload yielded, plus what it could not."""

    ticker: str
    facts: list[FinancialFact] = field(default_factory=list)
    periods: list[periods.AnnualPeriod] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    taxonomy: str | None = None
    split_events: list = field(default_factory=list)

    def for_period(self, label: str) -> list[FinancialFact]:
        return [f for f in self.facts if f.fiscal_period == label]

    def current(self) -> list[FinancialFact]:
        return [f for f in self.facts if f.is_current]


def utc_now() -> ISOTimestamp:
    """Current UTC instant in the contract's timestamp form."""
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_fact_id(
    ticker: Ticker, metric: str, fiscal_period: str, suffix: str | None = None
) -> str:
    """Deterministic fact id: fact:<TICKER>:<metric>:<period>[:<suffix>].

    Stable across runs for the same input, so a citation in a stored report keeps
    resolving. The suffix marks an as-filed row that a restatement superseded
    (the superseding accession), or the concept behind a debt component.
    """
    parts = [f"fact:{ticker}", metric, fiscal_period]
    if suffix:
        parts.append(suffix)
    return ":".join(parts)


def filing_type_of(form: str) -> tuple[FilingType | None, str]:
    """(contract enum, raw form). 10-K/A is a 10-K; the raw form is kept."""
    base = (form or "").split("/")[0]
    try:
        return FilingType(base), form
    except ValueError:
        return None, form


def source_url_for(cik: str | None, accession: str | None) -> str | None:
    """Link to the filing's index page, so a number in the UI is clickable."""
    if not cik or not accession:
        return None
    return FILING_INDEX_URL.format(
        cik=str(cik).lstrip("0"), nodash=accession.replace("-", ""), accession=accession
    )


# --------------------------------------------------------------------------
# reading companyfacts
# --------------------------------------------------------------------------
def annual_entries(
    companyfacts: dict, concept: str, taxonomy: str = US_GAAP, as_of: ISODate | None = None
) -> list[dict]:
    """Annual 10-K entries for one concept, oldest filing first.

    Filters to consolidated facts, annual forms, `fp == FY`, and - for a
    duration - a span of one fiscal year. Anything filed after `as_of` is
    invisible (ADR 0003).
    """
    node = (companyfacts.get("facts") or {}).get(taxonomy, {}).get(concept)
    if not node:
        return []

    out: list[dict] = []
    for unit, entries in (node.get("units") or {}).items():
        for entry in entries:
            if entry.get("form") not in periods.ANNUAL_FORMS or entry.get("fp") != "FY":
                continue
            if not dimensions.is_consolidated(entry):
                continue
            end, start = entry.get("end"), entry.get("start")
            if not end:
                continue
            if start and not periods.is_annual_duration(start, end):
                continue
            filed = entry.get("filed")
            if as_of and filed and filed > as_of:
                continue
            row = dict(entry)
            row["unit"] = unit
            row["concept"] = concept
            out.append(row)

    out.sort(key=lambda e: (e.get("filed") or "", e.get("accn") or ""))
    return out


def _index_by_period(
    companyfacts: dict, taxonomy: str, as_of: ISODate | None
) -> dict[str, dict[str, list[dict]]]:
    """concept -> period_end -> entries (oldest filing first)."""
    index: dict[str, dict[str, list[dict]]] = {}
    for concept in concept_map.all_concepts(taxonomy):
        entries = annual_entries(companyfacts, concept, taxonomy, as_of)
        if not entries:
            continue
        by_end: dict[str, list[dict]] = {}
        for entry in entries:
            by_end.setdefault(entry["end"], []).append(entry)
        index[concept] = by_end
    return index


def _pick(
    index: dict[str, dict[str, list[dict]]], concept: str, period_end: str
) -> list[dict] | None:
    """Every filed version of one concept at one period end, oldest first."""
    return (index.get(concept) or {}).get(period_end)


# --------------------------------------------------------------------------
# fact construction
# --------------------------------------------------------------------------
def _fact_from_entry(
    ticker: Ticker,
    metric: str,
    entry: dict,
    period: periods.AnnualPeriod,
    *,
    cik: str | None,
    retrieved_at: ISOTimestamp,
    fact_id: str,
) -> FinancialFact:
    """One reported XBRL value as a contract-valid fact."""
    concept = entry["concept"]
    value = float(entry["val"])
    if metric in concept_map.SIGN_FLIPPED and value < 0:
        # Stored POSITIVE meaning cash spent, so calc/ never has to guess.
        value = -value

    unit = UNIT_BY_XBRL.get(entry.get("unit", "USD"), Unit.USD)
    instant = metric in concept_map.INSTANT_METRICS
    filing_type, raw_form = filing_type_of(entry.get("form", ""))

    return FinancialFact(
        fact_id=fact_id,
        company_id=ticker,
        metric=metric,
        xbrl_concept=concept,
        value=value,
        unit=unit,
        currency="USD" if unit in (Unit.USD, Unit.USD_PER_SHARE) else None,
        scale="units",
        period_type=PeriodType.INSTANT if instant else PeriodType.DURATION,
        period_start=None if instant else (entry.get("start") or period.period_start),
        period_end=entry["end"],
        fiscal_period=period.label,
        dimension=None,
        filing_type=filing_type,
        accession_number=entry.get("accn"),
        filed_at=entry.get("filed"),
        retrieved_at=retrieved_at,
        source_url=source_url_for(cik, entry.get("accn")),
        source_location=f"{US_GAAP}:{concept}",
        source_kind=SourceKind.XBRL_REPORTED,
        form_raw=raw_form,
    )


def _debt_facts(
    ticker: Ticker,
    components: tuple[concept_map.DebtComponent, ...],
    period: periods.AnnualPeriod,
    *,
    cik: str | None,
    retrieved_at: ISOTimestamp,
) -> list[FinancialFact]:
    """Component facts plus the derived total.

    A single component means the filer reported a real total line, so it is
    emitted as `total_debt` directly - there is nothing to derive. Otherwise
    each part becomes its own fact and the total carries a Derivation naming
    them, because a summed number appears nowhere in the filing and a reader
    must be able to reach the lines that do.
    """
    if not components:
        return []

    entries = [dict(c.payload) for c in components]  # type: ignore[arg-type]
    for entry, component in zip(entries, components, strict=True):
        entry["concept"] = component.concept

    if len(components) == 1:
        return [
            _fact_from_entry(
                ticker,
                "total_debt",
                entries[0],
                period,
                cik=cik,
                retrieved_at=retrieved_at,
                fact_id=build_fact_id(ticker, "total_debt", period.label),
            )
        ]

    parts: list[FinancialFact] = []
    for entry in entries:
        parts.append(
            _fact_from_entry(
                ticker,
                DEBT_COMPONENT_METRIC,
                entry,
                period,
                cik=cik,
                retrieved_at=retrieved_at,
                fact_id=build_fact_id(
                    ticker, DEBT_COMPONENT_METRIC, period.label, entry["concept"]
                ),
            ).model_copy(update={restatements.IDENTITY_KEY: entry["concept"]})
        )

    total = sum(float(p.value or 0.0) for p in parts)
    newest = max(entries, key=lambda e: (e.get("filed") or ""))
    return [
        *parts,
        FinancialFact(
            fact_id=build_fact_id(ticker, "total_debt", period.label),
            company_id=ticker,
            metric="total_debt",
            xbrl_concept="+".join(e["concept"] for e in entries),
            value=total,
            unit=Unit.USD,
            currency="USD",
            scale="units",
            period_type=PeriodType.INSTANT,
            period_start=None,
            period_end=period.period_end,
            fiscal_period=period.label,
            filing_type=filing_type_of(newest.get("form", ""))[0],
            accession_number=newest.get("accn"),
            filed_at=newest.get("filed"),
            retrieved_at=retrieved_at,
            source_url=source_url_for(cik, newest.get("accn")),
            source_location=" + ".join(f"{US_GAAP}:{e['concept']}" for e in entries),
            source_kind=SourceKind.DERIVED,
            derivation=Derivation(
                formula=" + ".join(e["concept"] for e in entries),
                input_fact_ids=[p.fact_id for p in parts],
                computed_by=COMPUTED_BY,
            ),
            xbrl_parts=[
                {"concept": e["concept"], "value": float(e["val"]), "accession": e.get("accn")}
                for e in entries
            ],
        ),
    ]


# --------------------------------------------------------------------------
# the entry point
# --------------------------------------------------------------------------
def normalize_companyfacts(
    ticker: Ticker,
    companyfacts: dict,
    *,
    as_of: ISODate | None = None,
    retrieved_at: ISOTimestamp | None = None,
    years: int = 5,
    cik: str | None = None,
    taxonomy: str = US_GAAP,
) -> NormalizedFacts:
    """Five fiscal years of annual 10-K facts from one companyfacts payload.

    Point-in-time throughout: nothing filed after `as_of` is read at all, and
    for each fiscal period the value from the LATEST filing on or before `as_of`
    wins while every earlier version is kept and marked superseded
    (normalize.restatements).

    A filer with no `us-gaap` node - every 20-F/40-F filer - returns an empty
    result carrying a gap, never an exception.
    """
    retrieved_at = retrieved_at or utc_now()
    cik = cik or (str(companyfacts.get("cik")) if companyfacts.get("cik") else None)
    result = NormalizedFacts(ticker=ticker, taxonomy=taxonomy)

    available_taxonomies = list((companyfacts.get("facts") or {}).keys())
    if taxonomy not in available_taxonomies:
        result.taxonomy = None
        result.gaps.append(
            f"{ticker}: no {taxonomy} XBRL taxonomy "
            f"(found: {', '.join(available_taxonomies) or 'nothing'}). "
            "Foreign private issuers report under IFRS, which is not mapped."
        )
        return result

    index = _index_by_period(companyfacts, taxonomy, as_of)

    anchor_entries: list[dict] = []
    for metric in ANCHOR_METRICS:
        for concept in concept_map.candidates(metric, taxonomy):
            for entries in (index.get(concept) or {}).values():
                anchor_entries.extend(entries)

    calendar = periods.annual_periods(anchor_entries)
    if not calendar:
        result.gaps.append(
            f"{ticker}: no annual 10-K values found on or before {as_of or 'today'}."
        )
        return result

    result.periods = calendar[:years]

    for period in result.periods:
        for metric in concept_map.METRIC_CHAINS.get(taxonomy, {}):
            if metric in concept_map.NON_ANNUAL_METRICS:
                continue
            versions = None
            winner = None
            for concept in concept_map.candidates(metric, taxonomy):
                versions = _pick(index, concept, period.period_end)
                if versions:
                    winner = concept
                    break
            if not winner or not versions:
                result.gaps.append(f"{ticker} {period.label}: no concept matched {metric}")
                continue
            result.facts.extend(
                _versioned_facts(
                    ticker, metric, versions, period, cik=cik, retrieved_at=retrieved_at
                )
            )

        debt_available = {
            concept: versions[-1]
            for concept in concept_map.all_concepts(taxonomy)
            if (versions := _pick(index, concept, period.period_end))
        }
        components = concept_map.resolve_total_debt(debt_available, taxonomy)
        if components:
            result.facts.extend(
                _debt_facts(ticker, components, period, cik=cik, retrieved_at=retrieved_at)
            )
        else:
            result.gaps.append(f"{ticker} {period.label}: no concept matched total_debt")

    # Link every earlier filed version to the one that replaced it. Nothing is
    # dropped: the superseded rows are what a point-in-time query reads.
    result.facts = restatements.link(result.facts)

    # A split that was never applied back to an older period leaves a series
    # that is wrong by the split ratio while every value in it is as filed.
    result.gaps.extend(splits.detect_discontinuities(result.facts, result.periods))
    events = splits.split_events(companyfacts, taxonomy, as_of)
    adjusted, notes = splits.adjusted_facts(
        ticker, result.facts, result.periods, events, cik=cik, retrieved_at=retrieved_at
    )
    result.facts.extend(adjusted)
    result.gaps.extend(notes)
    result.split_events = events
    return result


def _versioned_facts(
    ticker: Ticker,
    metric: str,
    versions: list[dict],
    period: periods.AnnualPeriod,
    *,
    cik: str | None,
    retrieved_at: ISOTimestamp,
) -> list[FinancialFact]:
    """The current fact for a period, plus every earlier filed version of it.

    The newest filing wins; older ones keep their own row and are linked by
    normalize.restatements, because both are true statements about what was
    known when (ADR 0003).
    """
    current_entry = versions[-1]
    current = _fact_from_entry(
        ticker,
        metric,
        current_entry,
        period,
        cik=cik,
        retrieved_at=retrieved_at,
        fact_id=build_fact_id(ticker, metric, period.label),
    )
    out = [current]

    for entry in versions[:-1]:
        if float(entry["val"]) == float(current_entry["val"]):
            continue  # repeated unchanged in a later filing: not a restatement
        out.append(
            _fact_from_entry(
                ticker,
                metric,
                entry,
                period,
                cik=cik,
                retrieved_at=retrieved_at,
                fact_id=build_fact_id(
                    ticker, metric, period.label, (entry.get("accn") or "").replace("-", "")
                ),
            )
        )
    return out


def to_facts(
    ticker: Ticker, metric: str, payload: list[dict], concept: str, retrieved_at: ISOTimestamp
) -> list[FinancialFact]:
    """Turn resolved XBRL entries into contract-valid facts.

    Narrow entry point kept for one metric at a time; `normalize_companyfacts`
    is what the data layer actually calls.
    """
    calendar = periods.annual_periods(payload)
    by_end = {p.period_end: p for p in calendar}
    out: list[FinancialFact] = []
    for entry in payload:
        period = by_end.get(entry.get("end", ""))
        if period is None:
            continue
        row = dict(entry)
        row["concept"] = concept
        out.append(
            _fact_from_entry(
                ticker,
                metric,
                row,
                period,
                cik=None,
                retrieved_at=retrieved_at,
                fact_id=build_fact_id(ticker, metric, period.label),
            )
        )
    return out


def derive_fact(
    metric: str, formula: str, inputs: list[FinancialFact], value: float
) -> FinancialFact:
    """Build a DERIVED fact with full lineage.

    calc/ is the normal producer of derived facts; P1 uses this only for
    structural derivations such as a summed total debt.
    """
    if not inputs:
        raise ValueError(f"{metric}: a derived fact needs at least one input fact")
    newest = max(inputs, key=lambda f: (f.filed_at or "", f.accession_number or ""))
    return FinancialFact(
        fact_id=build_fact_id(newest.company_id, metric, newest.fiscal_period),
        company_id=newest.company_id,
        metric=metric,
        xbrl_concept="+".join(f.xbrl_concept or "" for f in inputs),
        value=value,
        unit=newest.unit,
        currency=newest.currency,
        scale="units",
        period_type=newest.period_type,
        period_start=newest.period_start,
        period_end=newest.period_end,
        fiscal_period=newest.fiscal_period,
        filing_type=newest.filing_type,
        accession_number=newest.accession_number,
        filed_at=newest.filed_at,
        retrieved_at=newest.retrieved_at,
        source_url=newest.source_url,
        source_location=formula,
        source_kind=SourceKind.DERIVED,
        derivation=Derivation(
            formula=formula,
            input_fact_ids=[f.fact_id for f in inputs],
            computed_by=COMPUTED_BY,
        ),
    )
