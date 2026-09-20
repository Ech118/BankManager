"""Build derived facts and value objects that carry their own lineage.

Specified by docs/adr/0002 and docs/verification.md.

Every number calc/ produces must record the formula and the inputs it came from.
That is not documentation: it is what lets audit/'s recompute check re-derive the
number independently and raise RECOMPUTE_MISMATCH when it disagrees. A computed
value with no lineage is unverifiable, so this module is the only sanctioned way
to make one.
"""

from __future__ import annotations

from datetime import UTC, datetime

from schema.contracts.common import ValueObject
from schema.contracts.enums import SourceKind, ValueStatus, ValueType
from schema.contracts.facts import Derivation, FinancialFact


def derived_value(
    value: float | None,
    unit: str,
    inputs: list[str],
    *,
    source_id: str | None = None,
    type_: ValueType = ValueType.FACT,
) -> ValueObject:
    """A ValueObject (type 'fact' by default) that lists what it was computed from.

    `value=None` produces an `unavailable` object: when an input is missing the
    answer is "we do not know", never 0. Pass `type_=ValueType.ESTIMATE` for a
    number derived from consensus/estimate inputs (e.g. forward P/E).
    """
    status = ValueStatus.OK if value is not None else ValueStatus.UNAVAILABLE
    return ValueObject(
        value=value,
        unit=unit,
        type=type_,
        status=status,
        source_id=source_id if value is not None else None,
        derived_from=list(inputs),
    )


def assumption_value(value: float, unit: str, name: str) -> ValueObject:
    """A ValueObject of type 'assumption', sourced to src:config:<name>.

    Used for every constant in calc/config.py, so the report can colour it
    differently from a reported fact.
    """
    return ValueObject(
        value=value,
        unit=unit,
        type=ValueType.ASSUMPTION,
        status=ValueStatus.OK,
        source_id=f"src:config:{name}",
    )


def derived_fact(
    metric: str, formula: str, inputs: list[FinancialFact], value: float
) -> FinancialFact:
    """A FinancialFact with source_kind 'derived' and a full Derivation.

    The contract rejects a derived fact without one, so this cannot be skipped.
    """
    if not inputs:
        raise ValueError(f"derived_fact({metric!r}): at least one input fact is required")
    base = inputs[0]
    fact_id = f"fact:{base.company_id}:{metric}:{base.fiscal_period}:derived"
    return FinancialFact(
        fact_id=fact_id,
        company_id=base.company_id,
        metric=metric,
        value=value,
        unit=base.unit,
        currency=base.currency,
        period_type=base.period_type,
        period_start=base.period_start,
        period_end=base.period_end,
        fiscal_period=base.fiscal_period,
        retrieved_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        source_kind=SourceKind.DERIVED,
        derivation=Derivation(
            formula=formula,
            input_fact_ids=[f.fact_id for f in inputs],
            computed_by="calc",
        ),
    )


def recompute(fact: FinancialFact, resolve) -> float | None:
    """Re-evaluate a derived fact from its inputs. The verifier's other half.

    Returns None when an input cannot be resolved, which the verifier reports as
    UNRESOLVED_FACT rather than as a mismatch.

    `resolve(fact_id) -> FinancialFact | None` is injected, so this module makes
    no assumption about where facts live.
    """
    if fact.source_kind is not SourceKind.DERIVED or fact.derivation is None:
        raise ValueError(f"{fact.fact_id}: recompute requires a derived fact with a derivation")

    values: dict[str, float] = {}
    for input_id in fact.derivation.input_fact_ids:
        resolved = resolve(input_id)
        if resolved is None or resolved.value is None:
            return None
        values[resolved.metric] = resolved.value

    try:
        return float(eval(fact.derivation.formula, {"__builtins__": {}}, values))  # noqa: S307
    except (NameError, SyntaxError, ZeroDivisionError, TypeError):
        return None
