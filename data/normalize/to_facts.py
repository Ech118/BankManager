"""Assemble FinancialFact rows from normalized XBRL payloads.

Specified by docs/data-model.md "From payload to fact".

The single place a FinancialFact is constructed from provider data, so the
provenance rules cannot be bypassed: every row gets its accession, filing date,
retrieval timestamp and the XBRL concept that actually matched.

Values are normalized to FULL UNITS here. `scale` records what the filing said
("millions") purely as provenance; no consumer ever multiplies by it again.

TODO(roadmap Step 1, P1).
"""

from __future__ import annotations

from schema.contracts.common import ISOTimestamp, Ticker
from schema.contracts.facts import FinancialFact


def build_fact_id(ticker: Ticker, metric: str, fiscal_period: str, suffix: str | None = None) -> str:
    """Deterministic fact id: fact:<TICKER>:<metric>:<period>[:<suffix>].

    Stable across runs for the same input, so a citation in a stored report keeps
    resolving. The suffix marks an as-filed row that a restatement superseded.
    """
    raise NotImplementedError("TODO(roadmap Step 1, P1)")


def to_facts(
    ticker: Ticker, metric: str, payload: list[dict], concept: str, retrieved_at: ISOTimestamp
) -> list[FinancialFact]:
    """Turn resolved XBRL entries into contract-valid facts.

    Drops dimensioned entries, flips the sign of outflow concepts listed in
    concept_map.SIGN_FLIPPED, and emits an `unavailable` fact rather than
    skipping a metric, so a gap is visible instead of silent.
    """
    raise NotImplementedError("TODO(roadmap Step 1, P1)")


def derive_fact(
    metric: str, formula: str, inputs: list[FinancialFact], value: float
) -> FinancialFact:
    """Build a DERIVED fact with full lineage.

    calc/ is the normal producer of derived facts; P1 uses this only for
    structural derivations such as Q4 = FY minus nine-month YTD.
    """
    raise NotImplementedError("TODO(roadmap Step 2, P1)")
