"""Stock-based compensation and share-count dilution.

Specified by docs/data-model.md and docs/verification.md (adjusted_as_gaap).

This pair answers "is EPS growth real?". A company can grow EPS with no
operating improvement at all by buying back stock, and can flatter operating
income by excluding a compensation expense it pays every year. Both are legal,
disclosed, and easy to miss in a summary, so both are computed explicitly rather
than left for an agent to notice.

`dilution_yoy` is negative when the share count SHRANK.
"""

from __future__ import annotations

from calc._util import div, num, ratio_minus_one
from calc.lineage import derived_value
from calc.metrics.fcf import free_cash_flow
from schema.contracts.common import ValueObject
from schema.contracts.factsheet import Factsheet


def dilution_yoy(factsheet: Factsheet, period: str, prior: str) -> ValueObject:
    """Change in diluted share count. Negative means buybacks shrank it."""
    cur, prev = factsheet.period(period), factsheet.period(prior)
    value = ratio_minus_one(
        num(cur.shares_diluted) if cur else None, num(prev.shares_diluted) if prev else None
    )
    return derived_value(value, "fraction",
                          [f"financials.{period}.shares_diluted", f"financials.{prior}.shares_diluted"])


def sbc_pct_revenue(factsheet: Factsheet, period: str) -> ValueObject:
    """SBC / revenue. Above config.SBC_REVENUE_FLAG raises a quality flag."""
    p = factsheet.period(period)
    value = div(num(p.sbc), num(p.revenue)) if p else None
    return derived_value(value, "fraction",
                          [f"financials.{period}.sbc", f"financials.{period}.revenue"])


def sbc_pct_fcf(factsheet: Factsheet, period: str) -> ValueObject:
    """SBC / FCF. The harsher framing: what share of cash generation is paid in stock."""
    p = factsheet.period(period)
    fcf = free_cash_flow(factsheet, period).value
    value = div(num(p.sbc) if p else None, fcf)
    return derived_value(value, "fraction", [f"financials.{period}.sbc", "cash_flow.fcf"])


def eps_growth_attribution(factsheet: Factsheet, period: str, prior: str) -> dict:
    """Split EPS growth into the part from earnings and the part from buybacks.

    Computed here rather than asserted by an agent: the mock audit fixture
    carries a warning about exactly this number being rounded by an agent
    instead of recomputed.

    Approximation: since eps = net_income / shares, (1 + eps_growth) ~=
    (1 + earnings_growth) / (1 + shares_growth). from_earnings is the net-income
    growth; from_buybacks is the residual.
    """
    cur, prev = factsheet.period(period), factsheet.period(prior)
    eps_growth = ratio_minus_one(
        num(cur.eps_diluted) if cur else None, num(prev.eps_diluted) if prev else None
    )
    earnings_growth = ratio_minus_one(
        num(cur.net_income) if cur else None, num(prev.net_income) if prev else None
    )
    from_buybacks = None if eps_growth is None or earnings_growth is None else eps_growth - earnings_growth
    return {
        "eps_growth": eps_growth,
        "from_earnings": earnings_growth,
        "from_buybacks": from_buybacks,
    }
