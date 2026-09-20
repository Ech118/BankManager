"""Valuation multiples: P/E, EV/EBITDA, EV/revenue, P/FCF.

Specified by docs/data-model.md "Valuation".

Enterprise value is recomputed from the market snapshot rather than trusted:
market_cap + total_debt - cash, from ONE snapshot instant. The verifier
re-derives it and raises RECOMPUTE_MISMATCH on drift.
"""

from __future__ import annotations

from calc._util import div, num
from calc.lineage import derived_value
from schema.contracts.common import ValueObject
from schema.contracts.enums import ValueType
from schema.contracts.factsheet import Factsheet


def enterprise_value(factsheet: Factsheet) -> ValueObject:
    """market_cap + total_debt - cash, all from one snapshot."""
    m = factsheet.market
    market_cap, total_debt, cash = num(m.market_cap), num(m.total_debt), num(m.cash)
    value = None if market_cap is None or total_debt is None or cash is None else \
        market_cap + total_debt - cash
    return derived_value(value, "usd",
                          ["market.market_cap", "market.total_debt", "market.cash"])


def price_to_earnings(factsheet: Factsheet, period: str) -> ValueObject:
    """Trailing P/E from the latest full year's diluted EPS."""
    p = factsheet.period(period)
    price = num(factsheet.market.price)
    eps = num(p.eps_diluted) if p else None
    return derived_value(div(price, eps), "multiple",
                          ["market.price", f"financials.{period}.eps_diluted"])


def forward_pe(factsheet: Factsheet) -> ValueObject:
    """Price / consensus next-FY EPS. Type ESTIMATE, never 'fact'."""
    price = num(factsheet.market.price)
    eps_next = num(factsheet.consensus.eps_next_fy) if factsheet.consensus else None
    value = div(price, eps_next)
    return derived_value(value, "multiple", ["market.price", "consensus.eps_next_fy"],
                          type_=ValueType.ESTIMATE)


def ev_ebitda(factsheet: Factsheet, ebitda_value: float | None) -> ValueObject:
    ev = enterprise_value(factsheet).value
    return derived_value(div(ev, ebitda_value), "multiple",
                          ["market.enterprise_value", "cash_flow.ebitda"])


def ev_revenue(factsheet: Factsheet, period: str) -> ValueObject:
    p = factsheet.period(period)
    ev = enterprise_value(factsheet).value
    revenue = num(p.revenue) if p else None
    return derived_value(div(ev, revenue), "multiple",
                          ["market.enterprise_value", f"financials.{period}.revenue"])


def price_to_fcf(factsheet: Factsheet, fcf_value: float | None) -> ValueObject:
    market_cap = num(factsheet.market.market_cap)
    return derived_value(div(market_cap, fcf_value), "multiple",
                          ["market.market_cap", "cash_flow.fcf"])
