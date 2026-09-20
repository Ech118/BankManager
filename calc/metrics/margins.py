"""Margin computation. Specified by docs/data-model.md.

All margins are FRACTIONS (0.40 means 40%). The contract rejects anything above
10 for a fraction unit, so a percent that escapes conversion fails loudly rather
than travelling into the report.
"""

from __future__ import annotations

from calc._util import div, num, sub
from calc.lineage import derived_value
from schema.contracts.factsheet import Factsheet
from schema.contracts.metrics import Margins


def margins_for(factsheet: Factsheet, period: str) -> Margins:
    """Gross, operating, net and FCF margin for one period."""
    p = factsheet.period(period)
    revenue = num(p.revenue) if p else None
    d = lambda *fields: [f"financials.{period}.{f}" for f in fields]  # noqa: E731

    if p is None:
        unavailable = derived_value(None, "fraction", [])
        return Margins(gross=unavailable, operating=unavailable, net=unavailable, fcf=unavailable)

    fcf = sub(num(p.op_cash_flow), num(p.capex))
    return Margins(
        gross=derived_value(div(num(p.gross_profit), revenue), "fraction",
                             d("gross_profit", "revenue")),
        operating=derived_value(div(num(p.operating_income), revenue), "fraction",
                                 d("operating_income", "revenue")),
        net=derived_value(div(num(p.net_income), revenue), "fraction",
                           d("net_income", "revenue")),
        fcf=derived_value(div(fcf, revenue), "fraction",
                           d("op_cash_flow", "capex", "revenue")),
    )


def all_margins(factsheet: Factsheet) -> dict[str, Margins]:
    """Margins for every reported period, keyed by period label."""
    return {p.period: margins_for(factsheet, p.period) for p in factsheet.financials}
