"""Build derived facts and value objects that carry their own lineage.

Specified by docs/adr/0002 and docs/verification.md.

Every number calc/ produces must record the formula and the inputs it came from.
That is not documentation: it is what lets audit/'s recompute check re-derive the
number independently and raise RECOMPUTE_MISMATCH when it disagrees. A computed
value with no lineage is unverifiable, so this module is the only sanctioned way
to make one.

TODO(roadmap Step 2, P2).
"""

from __future__ import annotations

from schema.contracts.common import ValueObject
from schema.contracts.facts import FinancialFact


def derived_value(
    value: float | None, unit: str, inputs: list[str], *, source_id: str | None = None
) -> ValueObject:
    """A ValueObject of type 'fact' that lists what it was computed from.

    `value=None` produces an `unavailable` object: when an input is missing the
    answer is "we do not know", never 0.
    """
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def assumption_value(value: float, unit: str, name: str) -> ValueObject:
    """A ValueObject of type 'assumption', sourced to src:config:<name>.

    Used for every constant in calc/config.py, so the report can colour it
    differently from a reported fact.
    """
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def derived_fact(
    metric: str, formula: str, inputs: list[FinancialFact], value: float
) -> FinancialFact:
    """A FinancialFact with source_kind 'derived' and a full Derivation.

    The contract rejects a derived fact without one, so this cannot be skipped.
    """
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def recompute(fact: FinancialFact, resolve: object) -> float | None:
    """Re-evaluate a derived fact from its inputs. The verifier's other half.

    Returns None when an input cannot be resolved, which the verifier reports as
    UNRESOLVED_FACT rather than as a mismatch.
    """
    raise NotImplementedError("TODO(roadmap Step 2, P2)")
