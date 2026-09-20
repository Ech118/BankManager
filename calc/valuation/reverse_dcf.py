"""Reverse DCF: what growth does today's price already assume?

Specified by docs/data-model.md and docs/adr/0001.

The most useful question in the product. A forward DCF asks "what is it worth?",
which mostly returns the analyst's own assumptions. A reverse DCF asks "what
would have to be true for today's price to be right?" and hands the LLM
something it is actually good at: judging whether that is plausible given the
filings.

Solves for the FCF growth rate that makes PV equal enterprise value, by
bisection on a monotonic function.
"""

from __future__ import annotations

from calc import config
from calc.lineage import assumption_value, derived_value
from calc.valuation.dcf import _solve_growth, sensitivity_grid
from calc.valuation.multiples import enterprise_value
from schema.contracts.factsheet import Factsheet
from schema.contracts.metrics import DcfAssumptions, ReverseDcf


def implied_growth(
    ev: float,
    fcf0: float,
    discount_rate: float,
    terminal_growth: float,
    years: int,
) -> float:
    """Bisect for the growth rate whose PV equals `ev` (enterprise value)."""
    g = _solve_growth(ev, fcf0, discount_rate, terminal_growth, years)
    if g is None:
        raise ValueError(
            "cannot solve implied growth: fcf0 must be positive and "
            "discount_rate must exceed terminal_growth"
        )
    return g


def reverse_dcf(factsheet: Factsheet, fcf_value: float | None, assumptions: dict | None = None) -> ReverseDcf:
    """Implied FCF CAGR plus the full sensitivity grid.

    `assumptions` may override config.py, and overrides are tagged ASSUMPTION
    with a src:config: source so the report can colour them.

    Takes the already-computed FCF value directly (not a full Metrics object)
    so this can run both standalone (calc.api.reverse_dcf) and as part of
    compute_metrics, before a Metrics instance exists.
    """
    assumptions = assumptions or {}
    discount_rate = assumptions.get("discount_rate", config.DISCOUNT_RATE)
    terminal_growth = assumptions.get("terminal_growth", config.TERMINAL_GROWTH)
    horizon_years = assumptions.get("horizon_years", config.DCF_HORIZON_YEARS)

    ev = enterprise_value(factsheet).value
    implied = _solve_growth(ev, fcf_value, discount_rate, terminal_growth, horizon_years)

    return ReverseDcf(
        implied_fcf_cagr=derived_value(implied, "fraction",
                                        ["market.enterprise_value", "cash_flow.fcf"]),
        assumptions=DcfAssumptions(
            discount_rate=assumption_value(discount_rate, "fraction", "calc_assumptions"),
            terminal_growth=assumption_value(terminal_growth, "fraction", "calc_assumptions"),
            horizon_years=horizon_years,
        ),
        sensitivity_grid=sensitivity_grid(fcf_value, ev, horizon_years),
    )
