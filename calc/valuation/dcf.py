"""Discounted cash flow. Specified by docs/data-model.md and docs/adr/0001.

Every output is dominated by its assumptions, so every output ships with a
sensitivity grid. A single headline number would imply a precision this method
does not have (error D).
"""

from __future__ import annotations

from calc import config
from calc.lineage import derived_value
from schema.contracts.metrics import SensitivityRow

SOLVE_LOW = -0.5
SOLVE_HIGH = 1.0
SOLVE_ITERATIONS = 200


def present_value(
    fcf0: float, growth: float, discount_rate: float, terminal_growth: float, years: int
) -> float:
    """PV of a growing FCF stream plus a terminal value.

    Requires terminal_growth < discount_rate; otherwise the terminal value is
    infinite and the model is meaningless. Raises ValueError rather than
    returning a huge number that looks like an answer.
    """
    if fcf0 <= 0:
        raise ValueError("fcf0 must be positive for a reverse DCF to be well-posed")
    if terminal_growth >= discount_rate:
        raise ValueError(
            f"terminal_growth {terminal_growth} must be below discount_rate {discount_rate}"
        )
    total, fcf = 0.0, fcf0
    for t in range(1, years + 1):
        fcf *= 1 + growth
        total += fcf / (1 + discount_rate) ** t
    terminal = fcf * (1 + terminal_growth) / (discount_rate - terminal_growth) / (1 + discount_rate) ** years
    return total + terminal


def _solve_growth(
    target_value: float | None, fcf0: float | None, discount_rate: float, terminal_growth: float,
    years: int,
) -> float | None:
    """Bisection helper shared with valuation/reverse_dcf.py. None on ill-posed input."""
    if target_value is None or fcf0 is None or fcf0 <= 0 or discount_rate <= terminal_growth:
        return None
    lo, hi = SOLVE_LOW, SOLVE_HIGH
    for _ in range(SOLVE_ITERATIONS):
        mid = (lo + hi) / 2
        pv = present_value(fcf0, mid, discount_rate, terminal_growth, years)
        lo, hi = (lo, mid) if pv > target_value else (mid, hi)
    return (lo + hi) / 2


def sensitivity_grid(fcf0: float | None, target_value: float | None, years: int) -> list[SensitivityRow]:
    """Solve across the config.py discount-rate and terminal-growth axes.

    The spread across this grid is the honest answer; the centre cell alone is
    not.
    """
    grid = []
    for r in config.SENSITIVITY_DISCOUNT_RATES:
        for tg in config.SENSITIVITY_TERMINAL_GROWTHS:
            g = _solve_growth(target_value, fcf0, r, tg, years)
            grid.append(SensitivityRow(
                discount_rate=r,
                terminal_growth=tg,
                implied_fcf_cagr=derived_value(g, "fraction",
                                                ["market.enterprise_value", "cash_flow.fcf"]),
            ))
    return grid
