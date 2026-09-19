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

TODO(roadmap Step 2, P1).
"""

from __future__ import annotations

from schema.contracts.facts import FinancialFact


def find_restatements(existing: list[FinancialFact], incoming: list[FinancialFact]) -> list[tuple[str, str]]:
    """Return (old_fact_id, new_fact_id) pairs where a value was restated.

    Two facts describe the same quantity when company, metric, fiscal_period,
    period_type and dimension all match. If the values differ and the incoming
    fact was filed later, the existing one is superseded.
    """
    raise NotImplementedError("TODO(roadmap Step 2, P1)")


def apply_supersessions(facts: list[FinancialFact], pairs: list[tuple[str, str]]) -> list[FinancialFact]:
    """Set `superseded_by` on the older facts. Never deletes a row."""
    raise NotImplementedError("TODO(roadmap Step 2, P1)")


def current_only(facts: list[FinancialFact]) -> list[FinancialFact]:
    """Facts no later filing has corrected. The default view for agents."""
    return [f for f in facts if f.is_current]
