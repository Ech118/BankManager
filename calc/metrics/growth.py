"""Year-over-year growth. Specified by docs/data-model.md.

Only emitted where a genuinely comparable prior period exists. Comparing a
quarter to a full year, or to a quarter of a different length, produces a number
that looks meaningful and is not, so the absence of a comparable prior yields no
entry rather than a plausible-looking one.
"""

from __future__ import annotations

from calc._util import num, ratio_minus_one, sub
from calc.lineage import derived_value
from schema.contracts.factsheet import Factsheet
from schema.contracts.metrics import Growth


def comparable_prior(factsheet: Factsheet, period: str) -> str | None:
    """The prior period of the same TYPE and length, or None."""
    if period.startswith("FY"):
        candidate = f"FY{int(period[2:]) - 1}"
    elif "-" in period:
        q, year = period.split("-", 1)
        candidate = f"{q}-{int(year) - 1}"
    else:
        return None
    return candidate if factsheet.period(candidate) is not None else None


def growth_for(factsheet: Factsheet, period: str, prior: str) -> Growth:
    """Revenue, EPS and FCF growth between two comparable periods."""
    cur, prev = factsheet.period(period), factsheet.period(prior)
    d = lambda cur_fields, prev_fields: (  # noqa: E731
        [f"financials.{period}.{f}" for f in cur_fields]
        + [f"financials.{prior}.{f}" for f in prev_fields]
    )
    fcf_cur = sub(num(cur.op_cash_flow), num(cur.capex)) if cur else None
    fcf_prev = sub(num(prev.op_cash_flow), num(prev.capex)) if prev else None
    return Growth(
        revenue_yoy=derived_value(
            ratio_minus_one(num(cur.revenue) if cur else None, num(prev.revenue) if prev else None),
            "fraction", d(["revenue"], ["revenue"])),
        eps_yoy=derived_value(
            ratio_minus_one(num(cur.eps_diluted) if cur else None, num(prev.eps_diluted) if prev else None),
            "fraction", d(["eps_diluted"], ["eps_diluted"])),
        fcf_yoy=derived_value(
            ratio_minus_one(fcf_cur, fcf_prev), "fraction",
            d(["op_cash_flow", "capex"], ["op_cash_flow", "capex"])),
    )


def all_growth(factsheet: Factsheet) -> dict[str, Growth]:
    """Growth for every period that has a comparable prior."""
    out: dict[str, Growth] = {}
    for p in factsheet.financials:
        prior = comparable_prior(factsheet, p.period)
        if prior is not None:
            out[p.period] = growth_for(factsheet, p.period, prior)
    return out
