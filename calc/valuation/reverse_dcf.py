"""Reverse DCF: what growth does today's price already imply?

Ported from `origin/p2-calc:calc/dcf.py` (the v1 branch) onto the v2 contracts.

This is the expectations-vs-reality check that makes the Valuation Agent useful
(docs/pipeline.md stage 3). "What is it worth?" mostly returns the analyst's own
assumptions; "what would have to be true for this price to be right?" is a
question the filings can answer. Code solves for the implied growth; the LLM only
judges whether the filings support it.

A single point answer would hide how much the result depends on the discount
rate, so `sensitivity_grid` is always populated and never a single cell
(ADR 0001, error D).
"""

from __future__ import annotations

from calc import config
from calc.facts import Ledger
from calc.lineage import assumption_value

NON_ARITHMETIC = {
    "recomputable": False,
    "method": "bisection on the discounted cash flow identity",
}
"""Marks a derivation the verifier cannot re-evaluate as an expression.

A bisection is not a formula, so audit/ must report it as "not recomputable"
rather than silently treating an unresolvable derivation as agreement.
"""


def _pv_at_growth(g: float, r: float, tg: float, fcf0: float, n: int) -> float:
    """PV of an FCF stream growing at g for n years, plus a Gordon terminal value."""
    total = 0.0
    fcf = fcf0
    for _ in range(1, n + 1):
        fcf *= 1 + g
        total += fcf / (1 + r) ** _
    terminal = fcf * (1 + tg) / (r - tg) / (1 + r) ** n
    return total + terminal


def solve_implied_growth(
    enterprise_value: float | None,
    fcf0: float | None,
    discount_rate: float,
    terminal_growth: float,
    horizon_years: int,
) -> float | None:
    """Bisect for g where the discounted stream equals today's enterprise value.

    Returns None - never a guess - when the problem is ill-posed: non-positive
    starting FCF (nothing to grow), or a discount rate at or below the terminal
    growth rate (the terminal value diverges).
    """
    if enterprise_value is None or fcf0 is None or fcf0 <= 0:
        return None
    if discount_rate <= 0 or discount_rate <= terminal_growth:
        return None
    lo, hi = config.DCF_SOLVE_LOW, config.DCF_SOLVE_HIGH
    for _ in range(config.DCF_SOLVE_ITERATIONS):
        mid = (lo + hi) / 2
        if (
            _pv_at_growth(mid, discount_rate, terminal_growth, fcf0, horizon_years)
            > enterprise_value
        ):
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def present_value(
    fcf0: float | None,
    growth: float,
    discount_rate: float,
    terminal_growth: float,
    horizon_years: int,
) -> float | None:
    """The forward DCF: what the stream is worth under an assumed growth rate."""
    if fcf0 is None or fcf0 <= 0 or discount_rate <= terminal_growth:
        return None
    return _pv_at_growth(growth, discount_rate, terminal_growth, fcf0, horizon_years)


def reverse_dcf_block(
    ledger: Ledger,
    fcf: dict,
    *,
    period: str,
    assumptions: dict | None = None,
) -> dict:
    """The `reverse_dcf` block of Metrics: implied CAGR, assumptions, sensitivity."""
    assumptions = assumptions or {}
    discount_rate = float(assumptions.get("discount_rate", config.DISCOUNT_RATE))
    terminal_growth = float(assumptions.get("terminal_growth", config.TERMINAL_GROWTH))
    horizon_years = int(assumptions.get("horizon_years", config.DCF_HORIZON_YEARS))

    ev_ref = ledger.market_ref("enterprise_value")
    fcf_ref = ledger.derived_ref(fcf, "fcf")
    inputs = {"enterprise_value": ev_ref, "fcf": fcf_ref}
    paths = ["market.enterprise_value", "cash_flow.fcf"]
    ev = None if ev_ref is None else ev_ref.value
    fcf_value = None if fcf_ref is None else fcf_ref.value

    reason = None
    if fcf.get("not_applicable"):
        reason = (
            "not applicable to a bank, insurer, broker or REIT: neither enterprise "
            "value nor free cash flow describes this balance sheet"
        )
    elif ev is None:
        reason = "enterprise_value unavailable, so there is no price to solve against"
    elif fcf_value is None or fcf_value <= 0:
        reason = (
            "free cash flow is unavailable or not positive: there is no stream for a "
            "growth rate to apply to"
        )

    def cell(rate: float, growth: float, metric: str) -> dict:
        return ledger.emit(
            None if reason else solve_implied_growth(ev, fcf_value, rate, growth, horizon_years),
            metric=metric,
            period=period,
            unit="fraction",
            formula=(
                f"solve g: pv(fcf, g, r={rate}, tg={growth}, n={horizon_years}) == enterprise_value"
            ),
            inputs={k: v for k, v in inputs.items() if v is not None},
            paths=paths,
            period_type="instant",
            reason=reason,
            not_applicable=bool(fcf.get("not_applicable")),
            derivation_extra=NON_ARITHMETIC,
        )

    grid = [
        {
            "discount_rate": rate,
            "terminal_growth": growth,
            "implied_fcf_cagr": cell(
                rate, growth, f"implied_fcf_cagr_r{int(rate * 1000)}_g{int(growth * 1000)}"
            ),
        }
        for rate in config.SENSITIVITY_DISCOUNT_RATES
        for growth in config.SENSITIVITY_TERMINAL_GROWTHS
    ]

    return {
        "implied_fcf_cagr": cell(discount_rate, terminal_growth, "implied_fcf_cagr"),
        "assumptions": {
            "discount_rate": assumption_value(discount_rate, "fraction", config.CONFIG_SOURCE),
            "terminal_growth": assumption_value(terminal_growth, "fraction", config.CONFIG_SOURCE),
            "horizon_years": horizon_years,
        },
        "sensitivity_grid": grid,
    }
