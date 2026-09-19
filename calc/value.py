"""Value-object helpers shared by every calc/ module. No I/O, no LLM.

Mirrors schema/common.json#/$defs/value: a numeric leaf is either
status "ok" (value is a number, plus source_id or a non-empty derived_from)
or status "unavailable" (value is null). Missing inputs propagate as
"unavailable" - we NEVER substitute 0 and NEVER guess (plan.txt 15.6, error E).
"""
from __future__ import annotations

from typing import Iterable, Optional


def value(
    num: Optional[float],
    unit: str,
    type_: str = "fact",
    source_id: Optional[str] = None,
    derived_from: Optional[Iterable[str]] = None,
) -> dict:
    """Build one VALUE OBJECT. num=None -> unavailable (never 0)."""
    out = {
        "value": None if num is None else round(float(num), 10),
        "unit": unit,
        "type": type_,
        "status": "unavailable" if num is None else "ok",
        "source_id": None if num is None else source_id,
    }
    if derived_from:
        out["derived_from"] = list(derived_from)
    return out


def unavailable(unit: str, type_: str = "fact") -> dict:
    return value(None, unit, type_)


def read(period: dict, field: str) -> Optional[float]:
    """Read a reported field's numeric value out of a factsheet financial_period
    dict, or None if missing/unavailable. Never raises on missing data."""
    vo = period.get(field) if period else None
    if not isinstance(vo, dict) or vo.get("status") != "ok":
        return None
    return vo["value"]


def vo_value(vo: Optional[dict]) -> Optional[float]:
    """Read the numeric value out of an existing value object, or None."""
    if not isinstance(vo, dict) or vo.get("status") != "ok":
        return None
    return vo["value"]


def div(num: Optional[float], den: Optional[float]) -> Optional[float]:
    """Safe division. None if either input is missing or den == 0 (never guess)."""
    if num is None or den is None or den == 0:
        return None
    return num / den


def sub(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    return a - b


def add(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    return a + b


def ratio_minus_one(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """a / b - 1, safe."""
    d = div(a, b)
    return None if d is None else d - 1


def median(xs: list[float]) -> Optional[float]:
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2
