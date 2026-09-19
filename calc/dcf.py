"""Reverse DCF: solve for the constant annual FCF growth rate that makes a
discounted FCF stream + Gordon-growth terminal value equal today's enterprise
value. This is the "expectations vs reality" check (plan.txt error 8 / D):
code solves for the growth the price implies, the LLM only judges whether
that growth is plausible.
"""
from __future__ import annotations

from typing import Optional

from calc import config
from calc.value import div, value


def _pv_at_growth(g: float, r: float, tg: float, fcf0: float, n: int) -> float:
    """PV of a FCF stream growing at g for n years, discounted at r, plus a
    Gordon-growth terminal value (growth tg forever) discounted back n years."""
    total = 0.0
    fcf = fcf0
    for t in range(1, n + 1):
        fcf *= 1 + g
        total += fcf / (1 + r) ** t
    terminal = fcf * (1 + tg) / (r - tg) / (1 + r) ** n
    return total + terminal


def solve_implied_growth(
    enterprise_value: float,
    fcf0: float,
    discount_rate: float,
    terminal_growth: float,
    horizon_years: int,
) -> Optional[float]:
    """Bisect for g such that _pv_at_growth(g, ...) == enterprise_value.

    Returns None (never guesses) if the inputs make the problem ill-posed:
    non-positive starting FCF, or discount_rate <= terminal_growth (terminal
    value diverges).
    """
    if enterprise_value is None or fcf0 is None or fcf0 <= 0:
        return None
    if discount_rate <= terminal_growth:
        return None
    lo, hi = config.DCF_SOLVE_LOW, config.DCF_SOLVE_HIGH
    if discount_rate <= 0:
        return None
    for _ in range(config.DCF_SOLVE_ITERATIONS):
        mid = (lo + hi) / 2
        pv = _pv_at_growth(mid, discount_rate, terminal_growth, fcf0, horizon_years)
        if pv > enterprise_value:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def compute_reverse_dcf(
    enterprise_value: Optional[float],
    fcf: Optional[float],
    assumptions: Optional[dict] = None,
) -> dict:
    """Return the metrics.json `reverse_dcf` block: implied_fcf_cagr,
    assumptions (tagged "assumption"), and a sensitivity_grid (plan.txt error D:
    "Always output a sensitivity grid, never a single point value")."""
    assumptions = assumptions or {}
    discount_rate = assumptions.get("discount_rate", config.DEFAULT_DISCOUNT_RATE)
    terminal_growth = assumptions.get("terminal_growth", config.DEFAULT_TERMINAL_GROWTH)
    horizon_years = assumptions.get("horizon_years", config.DEFAULT_DCF_HORIZON_YEARS)

    implied = solve_implied_growth(enterprise_value, fcf, discount_rate, terminal_growth, horizon_years)

    grid = []
    for r in config.DCF_SENSITIVITY_DISCOUNT_RATES:
        for tg in config.DCF_SENSITIVITY_TERMINAL_GROWTHS:
            g = solve_implied_growth(enterprise_value, fcf, r, tg, horizon_years)
            grid.append({
                "discount_rate": r,
                "terminal_growth": tg,
                "implied_fcf_cagr": value(
                    g, "fraction", "fact",
                    derived_from=["market.enterprise_value", "cash_flow.fcf"],
                ),
            })

    return {
        "implied_fcf_cagr": value(
            implied, "fraction", "fact",
            derived_from=["market.enterprise_value", "cash_flow.fcf"],
        ),
        "assumptions": {
            "discount_rate": value(discount_rate, "fraction", "assumption", config.SOURCE_CONFIG),
            "terminal_growth": value(terminal_growth, "fraction", "assumption", config.SOURCE_CONFIG),
            "horizon_years": horizon_years,
        },
        "sensitivity_grid": grid,
    }
