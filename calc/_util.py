"""Private numeric helpers shared across calc/'s internal modules.

Not part of the public interface (calc/api.py only). Safe arithmetic that
propagates a missing input as None rather than guessing (plan/CLAUDE.md:
"a missing input yields unavailable, never 0").
"""

from __future__ import annotations

from schema.contracts.common import ValueObject
from schema.contracts.enums import ValueStatus


def num(vo: ValueObject | None) -> float | None:
    """Read the numeric value out of a ValueObject, or None if unavailable."""
    if vo is None or vo.status is not ValueStatus.OK:
        return None
    return vo.value


def div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def sub(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return a - b


def add(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return a + b


def ratio_minus_one(a: float | None, b: float | None) -> float | None:
    d = div(a, b)
    return None if d is None else d - 1


def median(xs: list[float | None]) -> float | None:
    clean = sorted(x for x in xs if x is not None)
    if not clean:
        return None
    n = len(clean)
    return clean[n // 2] if n % 2 else (clean[n // 2 - 1] + clean[n // 2]) / 2
