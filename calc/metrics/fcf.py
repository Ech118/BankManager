"""Free cash flow and its derivatives. Specified by docs/data-model.md.

FCF = op_cash_flow - capex, with capex POSITIVE meaning cash spent (CLAUDE.md
sign conventions). P1 normalizes the sign, so nothing here has to guess.

`fcf_conversion` (FCF / net income) is the quiet one: a company whose reported
profit stops turning into cash is usually the first sign of an accounting
problem, well before anything shows up in the income statement.
"""

from __future__ import annotations

from calc._util import add, div, num, sub
from calc.lineage import derived_value
from schema.contracts.common import ValueObject
from schema.contracts.factsheet import Factsheet


def free_cash_flow(factsheet: Factsheet, period: str) -> ValueObject:
    """op_cash_flow - capex for one period."""
    p = factsheet.period(period)
    value = sub(num(p.op_cash_flow), num(p.capex)) if p else None
    return derived_value(value, "usd",
                          [f"financials.{period}.op_cash_flow", f"financials.{period}.capex"])


def fcf_conversion(factsheet: Factsheet, period: str) -> ValueObject:
    """FCF / net income. Below config.FCF_CONVERSION_FLAG raises a quality flag."""
    p = factsheet.period(period)
    fcf = free_cash_flow(factsheet, period).value
    ni = num(p.net_income) if p else None
    return derived_value(div(fcf, ni), "fraction",
                          ["cash_flow.fcf", f"financials.{period}.net_income"])


def fcf_yield(factsheet: Factsheet, period: str) -> ValueObject:
    """FCF / market cap. The valuation metric least sensitive to accounting choices."""
    fcf = free_cash_flow(factsheet, period).value
    market_cap = num(factsheet.market.market_cap)
    return derived_value(div(fcf, market_cap), "fraction", ["cash_flow.fcf", "market.market_cap"])


def capex_intensity(factsheet: Factsheet, period: str) -> ValueObject:
    """Capex / revenue. How much growth has to be bought."""
    p = factsheet.period(period)
    value = div(num(p.capex), num(p.revenue)) if p else None
    return derived_value(value, "fraction",
                          [f"financials.{period}.capex", f"financials.{period}.revenue"])


def ebitda(factsheet: Factsheet, period: str) -> ValueObject:
    """Operating income + D&A, UNADJUSTED.

    Deliberately not "adjusted EBITDA": every company adjusts differently, and
    an adjusted figure presented as a standard one is exactly what
    IssueType.ADJUSTED_AS_GAAP exists to catch.
    """
    p = factsheet.period(period)
    value = add(num(p.operating_income), num(p.depreciation_amortization)) if p else None
    return derived_value(value, "usd",
                          [f"financials.{period}.operating_income",
                           f"financials.{period}.depreciation_amortization"])
