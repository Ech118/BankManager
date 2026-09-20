"""Value-object and arithmetic helpers shared by every calc/ module.

Ported from the v1 branch (`origin/p2-calc:calc/value.py`) and extended for the
v2 contracts.

Mirrors `schema.contracts.common.ValueObject`: a numeric leaf is either
status "ok" (a number, plus a source_id or a non-empty derived_from) or status
"unavailable" (value null). A MISSING INPUT PROPAGATES AS UNAVAILABLE - calc/
never substitutes 0 and never guesses (CLAUDE.md conventions, ADR 0001).

Two extra keys ride along on an unavailable value, both tolerated by the
contract's `extra="allow"`:

  unavailable_reason  why there is no number, so the report can say so
  not_applicable      the metric does not describe this filer at all
                      (free cash flow for a bank), as opposed to merely missing

`not_applicable` matters because "we could not compute it" and "this number is
meaningless here" read identically as a null, and a reader deserves the
difference (P1 -> P2 request, 2026-09-19, section 2).
"""

from __future__ import annotations

from collections.abc import Iterable

from schema.contracts.common import FRACTION_SANITY_LIMIT

ROUND_DIGITS = 10
"""Every emitted number is rounded here so two runs of the same input are equal."""


def value(
    num: float | None,
    unit: str,
    type_: str = "fact",
    source_id: str | None = None,
    derived_from: Iterable[str] | None = None,
    *,
    reason: str | None = None,
    not_applicable: bool = False,
    fact_id: str | None = None,
) -> dict:
    """Build one ValueObject. `num=None` yields unavailable, never 0.

    A `fraction` whose magnitude passes FRACTION_SANITY_LIMIT is emitted as
    unavailable: the contract rejects it (0.25 means 25%, so 25 is a percent that
    escaped conversion), and a growth rate off a near-zero base is not a number
    anyone should read as 4000%.
    """
    if num is not None and unit == "fraction" and abs(num) > FRACTION_SANITY_LIMIT:
        reason = (
            f"computed fraction {num:.4g} exceeds the contract's sanity limit of "
            f"{FRACTION_SANITY_LIMIT:g}; the base period is too small for the ratio to mean anything"
        )
        num = None
    out: dict = {
        "value": None if num is None else round(float(num), ROUND_DIGITS),
        "unit": unit,
        "type": type_,
        "status": "unavailable" if num is None else "ok",
        "source_id": None if num is None else source_id,
    }
    if derived_from:
        out["derived_from"] = list(derived_from)
    if num is None:
        out["unavailable_reason"] = reason or "an input was unavailable"
        if not_applicable:
            out["not_applicable"] = True
    elif fact_id:
        out["fact_id"] = fact_id
    return out


def unavailable(
    unit: str,
    type_: str = "fact",
    reason: str | None = None,
    *,
    not_applicable: bool = False,
    derived_from: Iterable[str] | None = None,
) -> dict:
    """An explicitly missing value, with the reason attached."""
    return value(
        None, unit, type_, derived_from=derived_from, reason=reason, not_applicable=not_applicable
    )


def not_applicable(unit: str, reason: str, type_: str = "fact") -> dict:
    """A metric that does not describe this filer (FCF or EV for a bank)."""
    return value(None, unit, type_, reason=reason, not_applicable=True)


def read(period: dict | None, field: str) -> float | None:
    """Read a reported field out of one `financials[]` entry, or None.

    Never raises on missing data: an absent key, a null value and an
    `unavailable` status all come back as None.
    """
    vo = period.get(field) if period else None
    return vo_value(vo)


def vo_value(vo: dict | None) -> float | None:
    """The number inside an existing ValueObject, or None when unavailable."""
    if not isinstance(vo, dict) or vo.get("status") != "ok":
        return None
    val = vo.get("value")
    return None if val is None else float(val)


def div(num: float | None, den: float | None) -> float | None:
    """Safe division: None if either side is missing or the denominator is 0."""
    if num is None or den is None or den == 0:
        return None
    return num / den


def sub(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else a - b


def add(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else a + b


def mul(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else a * b


def ratio_minus_one(a: float | None, b: float | None) -> float | None:
    """a / b - 1. None when either side is missing, b is 0, or b is negative.

    A growth rate off a negative base has the wrong sign and reads as an
    improvement when the company got worse, so it is refused rather than shown.
    """
    if a is None or b is None or b <= 0:
        return None
    return a / b - 1


def cagr(latest: float | None, earliest: float | None, years: float) -> float | None:
    """Compound annual growth rate. None unless both ends are positive.

    A CAGR across a sign change is undefined, and a fractional-power root of a
    negative number is not real, so both cases yield unavailable.
    """
    if latest is None or earliest is None or years <= 0:
        return None
    if earliest <= 0 or latest <= 0:
        return None
    return (latest / earliest) ** (1.0 / years) - 1


def median(xs: Iterable[float | None]) -> float | None:
    """Median of the values that exist, or None when none do."""
    vals = sorted(x for x in xs if x is not None)
    if not vals:
        return None
    n = len(vals)
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2
