"""Restatement detection and superseded_by linking.

Specified by docs/sec-pitfalls.md "Restatements" and docs/adr/0003.

When a later filing reports a different value for a period already reported, the
earlier fact is not deleted - it is marked `superseded_by` the newer one. Both
rows stay, because both are true statements about what was known when.

This is what lets two questions have different answers:
  - "what is FY2024 operating cash flow?"        -> the current, restated fact
  - "what did we know on 2025-06-01?"            -> the as-filed fact
A system that keeps only the latest value cannot answer the second, and its
backtest is contaminated (error A).

WHERE THE HISTORY COMES FROM
    docs/sec-pitfalls.md says to use `companyconcept` because `companyfacts`
    "returns the latest value". Checked against the real payloads: companyfacts
    keeps EVERY filed version of a period, each with its own `accn` and `filed`.
    NVDA's year ending 2023-01-29 appears three times, from the FY2023, FY2024
    and FY2025 10-Ks.

    The trap is therefore narrower than the doc states: it bites only code that
    takes the last entry per period without reading `filed`. Since this module
    reads `filed`, one companyfacts fetch reconstructs the point-in-time history
    that would otherwise cost one companyconcept request per tag - about twenty
    requests per company against an 8 req/s budget.
"""

from __future__ import annotations

from schema.contracts.common import ISODate
from schema.contracts.facts import FinancialFact

IDENTITY_KEY = "identity_key"
"""Optional extra field naming a discriminator within one metric and period.

Most metrics are unique per period, so metric + period identifies the quantity.
Total debt's components are not: four `total_debt_component` rows share FY2025,
one per reported line. Without a discriminator, AAPL's CommercialPaper (7,979M)
would be treated as a restatement of its LongTermDebt (90,678M) - and the
smaller, equally current number would vanish from the truth layer.
"""


def identity(fact: FinancialFact) -> tuple:
    """What makes two facts descriptions of the SAME quantity."""
    dimension = tuple(sorted((fact.dimension or {}).items()))
    return (
        fact.company_id,
        fact.metric,
        fact.fiscal_period,
        fact.period_type,
        dimension,
        getattr(fact, IDENTITY_KEY, None),
    )


def find_restatements(
    existing: list[FinancialFact], incoming: list[FinancialFact]
) -> list[tuple[str, str]]:
    """Return (old_fact_id, new_fact_id) pairs where a value was restated.

    Two facts describe the same quantity when company, metric, fiscal_period,
    period_type and dimension all match. If the values differ and the incoming
    fact was filed later, the existing one is superseded.
    """
    by_identity: dict[tuple, list[FinancialFact]] = {}
    for fact in incoming:
        by_identity.setdefault(identity(fact), []).append(fact)

    pairs: list[tuple[str, str]] = []
    for old in existing:
        for new in by_identity.get(identity(old), []):
            if new.fact_id == old.fact_id:
                continue
            if (new.filed_at or "") <= (old.filed_at or ""):
                continue
            if new.value == old.value:
                continue
            pairs.append((old.fact_id, new.fact_id))
    return pairs


def link(facts: list[FinancialFact]) -> list[FinancialFact]:
    """Mark every superseded version within one list of facts.

    For each quantity, the value from the LATEST filing is current and every
    earlier filed version points at it. Order is preserved and nothing is
    dropped - the superseded rows are what a point-in-time query reads.
    """
    groups: dict[tuple, list[FinancialFact]] = {}
    for fact in facts:
        groups.setdefault(identity(fact), []).append(fact)

    superseded_by: dict[str, str] = {}
    for versions in groups.values():
        if len(versions) < 2:
            continue
        newest = max(versions, key=lambda f: (f.filed_at or "", f.accession_number or ""))
        for fact in versions:
            if fact.fact_id != newest.fact_id:
                superseded_by[fact.fact_id] = newest.fact_id

    if not superseded_by:
        return facts
    return [
        fact.model_copy(update={"superseded_by": superseded_by[fact.fact_id]})
        if fact.fact_id in superseded_by
        else fact
        for fact in facts
    ]


def apply_supersessions(
    facts: list[FinancialFact], pairs: list[tuple[str, str]]
) -> list[FinancialFact]:
    """Set `superseded_by` on the older facts. Never deletes a row."""
    mapping = dict(pairs)
    return [
        fact.model_copy(update={"superseded_by": mapping[fact.fact_id]})
        if fact.fact_id in mapping
        else fact
        for fact in facts
    ]


def as_known_on(facts: list[FinancialFact], as_of: ISODate) -> list[FinancialFact]:
    """The facts a run dated `as_of` may read: filed by then, latest version.

    Re-links supersession WITHIN the visible window, so a value that was later
    corrected still reads as current for a run that predates the correction.

    The existing `superseded_by` is CLEARED first. It points at a correction
    that had not been filed yet, and leaving it set would drop the as-filed row
    as stale - which is the contamination this whole module exists to prevent
    (ADR 0003), inverted: instead of seeing a number too early, the run would
    see no number at all.
    """
    visible = [
        f.model_copy(update={"superseded_by": None})
        for f in facts
        if not f.filed_at or f.filed_at <= as_of
    ]
    return current_only(link(visible))


def current_only(facts: list[FinancialFact]) -> list[FinancialFact]:
    """Facts no later filing has corrected. The default view for agents."""
    return [f for f in facts if f.is_current]
