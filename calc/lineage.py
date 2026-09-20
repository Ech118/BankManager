"""Build derived facts and value objects that carry their own lineage.

Specified by docs/adr/0002 and docs/verification.md.

Every number calc/ produces must record the formula and the inputs it came from.
That is not documentation: it is what lets audit/'s recompute check re-derive the
number independently and raise RECOMPUTE_MISMATCH when it disagrees. A computed
value with no lineage is unverifiable, so this module is the only sanctioned way
to make one.

Three rules live here, and nothing else in calc/ may implement them:

1. **filed_at is the LATEST filed_at among the inputs.** The derived value did
   not exist until its last input was filed, so anything earlier would leak it
   into a backtest dated before it was knowable (P1 -> P2 request 2026-09-20,
   ADR 0003).
2. **A derived fact is emitted only when it has a value.** An unavailable metric
   is an unavailable ValueObject with a reason, not a fact with a null in it.
3. **Every formula is re-evaluable.** `Derivation.variables` maps each name in
   the formula to the fact_id it came from, so `recompute` can rebuild the number
   without knowing which metric it is looking at.
"""

from __future__ import annotations

import ast
import operator
from collections.abc import Callable, Iterable, Mapping
from typing import Any, NamedTuple

from calc.value import value as _value

COMPUTED_BY = "calc"
"""Recorded on every Derivation. calc/ is the only legitimate producer."""


class FactRef(NamedTuple):
    """One input to a derived fact: where it came from and when it was filed."""

    fact_id: str
    metric: str
    period: str
    value: float | None
    filed_at: str | None


def _sanitize(period: str) -> str:
    """Q2-2026 -> Q2_2026, so a period can be part of a formula variable name."""
    return period.replace("-", "_").replace(".", "_")


def var_name(metric: str, period: str, *, qualify: bool) -> str:
    """The name a metric goes by inside a formula."""
    return f"{metric}_{_sanitize(period)}" if qualify else metric


def latest_filed_at(inputs: Iterable[FactRef]) -> str | None:
    """The rule: a derived fact is filed when its LAST input was filed.

    ISO 8601 dates sort lexicographically, so max() is the calendar maximum.
    Returns None only when no input carried a date at all.
    """
    dates = [ref.filed_at for ref in inputs if ref.filed_at]
    return max(dates) if dates else None


# --------------------------------------------------------------------------
# ValueObjects
# --------------------------------------------------------------------------
def derived_value(
    value: float | None,
    unit: str,
    inputs: list[str],
    *,
    source_id: str | None = None,
    value_type: str = "fact",
    reason: str | None = None,
    not_applicable: bool = False,
    fact_id: str | None = None,
) -> dict:
    """A ValueObject of type 'fact' that lists what it was computed from.

    `value=None` produces an `unavailable` object: when an input is missing the
    answer is "we do not know", never 0.

    `inputs` are the DOTTED PATHS a reader follows (financials.FY2025.revenue),
    which is what the report renders; `fact_id` points at the derived fact that
    carries the machine-checkable derivation.
    """
    return _value(
        value,
        unit,
        value_type,
        source_id=source_id,
        derived_from=inputs,
        reason=reason,
        not_applicable=not_applicable,
        fact_id=fact_id,
    )


def assumption_value(value: float, unit: str, name: str) -> dict:
    """A ValueObject of type 'assumption', sourced to src:config:<name>.

    Used for every constant in calc/config.py, so the report can colour it
    differently from a reported fact.
    """
    return _value(value, unit, "assumption", source_id=f"src:config:{name}")


# --------------------------------------------------------------------------
# Derived facts
# --------------------------------------------------------------------------
def derived_fact(
    metric: str,
    formula: str,
    inputs: Mapping[str, FactRef],
    value: float,
    *,
    company_id: str,
    period: str,
    period_end: str,
    period_type: str = "duration",
    period_start: str | None = None,
    unit: str = "usd",
    retrieved_at: str,
    fact_id: str | None = None,
    derivation_extra: Mapping[str, Any] | None = None,
) -> dict:
    """A FinancialFact with source_kind 'derived' and a full Derivation.

    The contract rejects a derived fact without one, so this cannot be skipped.
    `inputs` maps each variable in `formula` to the fact it was read from.
    """
    refs = list(inputs.values())
    fact: dict[str, Any] = {
        "fact_id": fact_id or f"fact:{company_id}:{metric}:{period}",
        "company_id": company_id,
        "metric": metric,
        "value": round(float(value), 10),
        "unit": unit,
        "currency": "USD" if unit in ("usd", "usd_per_share") else None,
        "period_type": period_type,
        "period_start": period_start if period_type == "duration" else None,
        "period_end": period_end,
        "fiscal_period": period,
        "filed_at": latest_filed_at(refs),
        "retrieved_at": retrieved_at,
        "source_kind": "derived",
        "source_location": f"calc:{metric}",
        "derivation": {
            "formula": formula,
            "input_fact_ids": [ref.fact_id for ref in refs],
            "computed_by": COMPUTED_BY,
            "variables": {name: ref.fact_id for name, ref in inputs.items()},
            **(dict(derivation_extra) if derivation_extra else {}),
        },
    }
    return fact


# --------------------------------------------------------------------------
# Recompute: the verifier's other half
# --------------------------------------------------------------------------
_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}


class UnresolvedInput(Exception):
    """Raised internally when a formula names a fact that cannot be resolved."""


def _eval(node: ast.AST, names: Mapping[str, float]) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body, names)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError(f"formula constant must be numeric, got {node.value!r}")
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id not in names:
            raise UnresolvedInput(node.id)
        return names[node.id]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        val = _eval(node.operand, names)
        return val if isinstance(node.op, ast.UAdd) else -val
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return _BINOPS[type(node.op)](_eval(node.left, names), _eval(node.right, names))
    raise ValueError(f"formula contains an unsupported expression: {ast.dump(node)}")


def evaluate_formula(formula: str, names: Mapping[str, float]) -> float | None:
    """Evaluate a Derivation formula over resolved input values.

    Arithmetic only - names, numbers, + - * / ** and parentheses. No calls, no
    attributes, no comparisons: a formula is a number, never a program.
    Returns None when the arithmetic is undefined (division by zero, or a
    fractional power of a negative number), which the caller reports as
    unavailable rather than as a mismatch.
    """
    tree = ast.parse(formula.strip(), mode="eval")
    try:
        result = _eval(tree, names)
    except ZeroDivisionError:
        return None
    if isinstance(result, complex):
        return None
    return float(result)


def recompute(fact: dict, resolve: Callable[[str], Any]) -> float | None:
    """Re-evaluate a derived fact from its inputs. The verifier's other half.

    Returns None when an input cannot be resolved, which the verifier reports as
    UNRESOLVED_FACT rather than as a mismatch.

    `resolve` takes a fact_id and returns either a number, None, or a fact dict.
    """
    derivation = fact.get("derivation") or {}
    formula = derivation.get("formula")
    if not formula:
        return None
    variables = derivation.get("variables")
    if not variables:
        # A derivation with no variable map can still be recomputed when each
        # input fact's metric name appears in the formula exactly once.
        variables = {}
        for fid in derivation.get("input_fact_ids", []):
            resolved = resolve(fid)
            metric = resolved.get("metric") if isinstance(resolved, dict) else None
            if not metric:
                return None
            variables[metric] = fid
    names: dict[str, float] = {}
    for name, fid in variables.items():
        resolved = resolve(fid)
        if isinstance(resolved, dict):
            resolved = resolved.get("value")
        if resolved is None:
            return None
        names[name] = float(resolved)
    try:
        return evaluate_formula(formula, names)
    except (UnresolvedInput, ValueError, OverflowError):
        return None
