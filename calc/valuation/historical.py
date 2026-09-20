"""Historical multiples: how the company's own valuation has moved.

Specified by docs/data-model.md "Valuation".

A company at 34x earnings against a five-year median of 22x is a different
proposition from one at 34x against a median of 33x, even when the peer
comparison is identical. This is the comparison that is hardest to get for free
(error E), so every output may legitimately be `unavailable`.

**Today every output IS unavailable**, with the reason `"no price history
source"`. Finnhub's free tier serves current quotes only, so there is no price
series to divide historical earnings into, and P2 will not manufacture one: a
"historical P/E" built from today's price and last year's EPS is not a historical
multiple, it is this year's multiple wearing a label that would mislead a reader
into a conclusion about re-rating.

The functions below are complete and take a series, so the day a price history
arrives - a vendor, a cached daily close, anything - this file needs no change:
only the caller that feeds it.
"""

from __future__ import annotations

from calc.value import median as _median
from calc.value import ratio_minus_one, unavailable, value, vo_value

NO_PRICE_HISTORY = "no price history source"
"""The single reason string, so the report and the tests agree on the wording."""

HISTORICAL_FIELDS = ("pe", "ev_ebitda", "p_fcf", "p_s")
"""The multiples a history would cover, in the order the report shows them."""


def historical_median(series: list[dict], unit: str = "multiple") -> dict:
    """Median of a company's own multiple over time."""
    values = [vo_value(vo) for vo in series or []]
    usable = [v for v in values if v is not None]
    if not usable:
        return unavailable(unit, reason=NO_PRICE_HISTORY)
    out = value(
        _median(usable),
        unit,
        "fact",
        derived_from=[f"valuation.history[{i}]" for i in range(len(series))],
    )
    out["observations"] = len(usable)
    return out


def premium_to_own_history(current: dict, history: list[dict], unit: str = "fraction") -> dict:
    """Premium (+) or discount (-) to the company's own historical median."""
    med = historical_median(history)
    if med.get("value") is None or vo_value(current) is None:
        return unavailable(unit, reason=med.get("unavailable_reason") or NO_PRICE_HISTORY)
    return value(
        ratio_minus_one(vo_value(current), med["value"]),
        unit,
        "fact",
        derived_from=["valuation.pe", "valuation.historical.median"],
    )


def historical_block(own: dict, history: dict | None = None) -> dict:
    """The `valuation.historical` block: one entry per multiple, plus the reason.

    `history` maps a multiple name to a list of past ValueObjects. Nothing
    produces one yet, so the default is empty and every entry is unavailable.
    """
    history = history or {}
    out: dict = {
        "available": False,
        "reason": NO_PRICE_HISTORY,
        "source_needed": (
            "a daily or monthly close series; Finnhub's free tier returns the current "
            "quote only, so this cannot be derived from the factsheet"
        ),
    }
    for field in HISTORICAL_FIELDS:
        series = history.get(field) or []
        out[field] = {
            "median": historical_median(series),
            "premium_to_median": premium_to_own_history(own.get(field) or {}, series),
        }
    out["available"] = any(out[f]["median"].get("value") is not None for f in HISTORICAL_FIELDS)
    if out["available"]:
        out.pop("reason", None)
        out.pop("source_needed", None)
    return out
