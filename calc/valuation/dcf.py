"""Discounted cash flow. Specified by docs/data-model.md and docs/adr/0001.

Every output is dominated by its assumptions, so every output ships with a
sensitivity grid. A single headline number would imply a precision this method
does not have (error D).

The growth rate is the whole model, so it is not invented here: it is the
company's own FCF CAGR over the reported span, **bounded** by
`config.DCF_MAX_ASSUMED_GROWTH`. NVDA's trailing FCF CAGR is 68%/yr, and
compounding that for ten years produces a number no one should publish, so the
clamp is recorded in the output rather than applied quietly - the same rule that
governs a scenario weight.
"""

from __future__ import annotations

from calc import config
from calc.facts import Ledger, present
from calc.lineage import assumption_value
from calc.valuation.reverse_dcf import NON_ARITHMETIC, present_value
from calc.value import div, value

NO_FCF = "no positive free cash flow to discount, so a DCF would be a projection of nothing"


def growth_input(ledger: Ledger, metrics: dict) -> dict:
    """The assumed growth rate, bounded, with the clamp recorded."""
    cagr = (metrics.get("cagr") or {}).get("fcf") or {}
    requested = cagr.get("value")
    cap = config.DCF_MAX_ASSUMED_GROWTH
    floored = False
    if requested is None:
        applied, source, note = (
            config.TERMINAL_GROWTH,
            "config",
            "no trailing FCF CAGR was computable, so the terminal growth rate is used "
            "for the explicit period too - a deliberately unambitious default",
        )
    elif requested < 0:
        # A single trailing window can be dominated by one event - Coca-Cola's
        # FY2024 IRS deposit turns its four-year FCF CAGR into -17%/yr. Projecting
        # that decline for ten years does not value the company, it values the
        # event, so a negative trailing CAGR is treated as NO growth information
        # and the substitution is recorded rather than applied quietly.
        applied, source, floored = config.TERMINAL_GROWTH, "floored_to_terminal", True
        note = (
            f"trailing FCF CAGR is negative ({requested:.1%}/yr), which one unusual year "
            f"can produce; the explicit period uses the terminal growth rate "
            f"({applied:.0%}) instead. The trailing figure is kept in `requested`."
        )
    else:
        applied = min(requested, cap)
        source = "trailing_fcf_cagr"
        note = (
            f"trailing FCF CAGR of {requested:.1%} exceeds the {cap:.0%} cap on an "
            f"assumed growth rate and was clamped to {applied:.0%}"
            if applied != requested
            else f"trailing FCF CAGR of {requested:.1%}, inside the {cap:.0%} cap"
        )
    out = assumption_value(applied, "fraction", config.CONFIG_SOURCE)
    out["requested"] = requested
    out["cap"] = cap
    out["was_clamped"] = requested is not None and applied != requested and not floored
    out["was_floored"] = floored
    out["basis"] = source
    out["note"] = note
    return out


def simple_dcf(ledger: Ledger, metrics: dict, assumptions: dict | None = None) -> dict:
    """A forward DCF on the same config the reverse DCF uses.

    Enterprise value, then equity value after net debt, then a per-share value and
    the upside to today's price. Every cell of the grid is a full valuation, not a
    single point sensitivity on one axis.
    """
    assumptions = assumptions or {}
    discount_rate = float(assumptions.get("discount_rate", config.DISCOUNT_RATE))
    terminal_growth = float(assumptions.get("terminal_growth", config.TERMINAL_GROWTH))
    horizon = int(assumptions.get("horizon_years", config.DCF_HORIZON_YEARS))

    fcf_vo = metrics["cash_flow"]["fcf"]
    fcf_ref = ledger.derived_ref(fcf_vo, "fcf")
    fcf = fcf_vo.get("value")
    growth = growth_input(ledger, metrics)
    period = metrics["latest_annual_period"]
    balance = metrics["latest_balance_period"]

    reason = None
    if fcf_vo.get("not_applicable"):
        reason = fcf_vo.get("unavailable_reason")
    elif fcf is None or fcf <= 0:
        reason = fcf_vo.get("unavailable_reason") or NO_FCF

    debt_ref = ledger.ref(balance, "total_debt")
    cash_ref = ledger.ref(balance, "cash")
    shares_ref = ledger.market_ref("shares_outstanding") or ledger.ref(period, "shares_diluted")
    price = ledger.market_ref("price")

    def valuation_at(rate: float, tg: float, metric: str) -> dict:
        ev = None if reason else present_value(fcf, growth["value"], rate, tg, horizon)
        equity = None
        if ev is not None and debt_ref is not None and cash_ref is not None:
            equity = ev - (debt_ref.value - cash_ref.value)
        why = reason
        if equity is not None and equity <= 0:
            # The discounted stream does not cover net debt. Arithmetically this is
            # a negative price per share, which is not a thing: equity is worth zero
            # at worst. Reporting the number would invite an agent to cite it.
            why = (
                f"the discounted stream is worth less than net debt (equity value "
                f"{equity:,.0f} USD at r={rate:.0%}, g={growth['value']:.1%}), so this "
                "model produces no per-share value for this company"
            )
            equity = None
        per_share = div(equity, shares_ref.value if shares_ref else None)
        inputs = present(
            {
                "fcf": fcf_ref,
                "total_debt": debt_ref,
                "cash": cash_ref,
                "shares_outstanding": shares_ref,
            }
        )
        return ledger.emit(
            per_share,
            metric=metric,
            period=period,
            unit="usd_per_share",
            formula=(
                f"(pv(fcf, g={growth['value']}, r={rate}, tg={tg}, n={horizon}) "
                "- (total_debt - cash)) / shares_outstanding"
            ),
            inputs=inputs,
            paths=[
                "cash_flow.fcf",
                f"financials.{balance}.total_debt",
                f"financials.{balance}.cash",
                "market.shares_outstanding",
            ],
            period_type="instant",
            value_type="estimate",
            reason=why
            or "net debt or the share count is unavailable, so no per-share value can be built",
            not_applicable=bool(fcf_vo.get("not_applicable")),
            derivation_extra=NON_ARITHMETIC,
        )

    fair_value = valuation_at(discount_rate, terminal_growth, "dcf_value_per_share")
    upside = None
    if fair_value.get("value") is not None and price is not None and price.value:
        upside = fair_value["value"] / price.value - 1

    grid = [
        {
            "discount_rate": rate,
            "terminal_growth": tg,
            "value_per_share": valuation_at(
                rate, tg, f"dcf_value_per_share_r{int(rate * 1000)}_g{int(tg * 1000)}"
            ),
        }
        for rate in config.SENSITIVITY_DISCOUNT_RATES
        for tg in config.SENSITIVITY_TERMINAL_GROWTHS
    ]

    return {
        "value_per_share": fair_value,
        "upside_to_price": value(
            upside,
            "fraction",
            "estimate",
            derived_from=["valuation.dcf.value_per_share", "market.price"],
            reason=fair_value.get("unavailable_reason") or "no price to compare against",
        ),
        "assumptions": {
            "discount_rate": assumption_value(discount_rate, "fraction", config.CONFIG_SOURCE),
            "terminal_growth": assumption_value(terminal_growth, "fraction", config.CONFIG_SOURCE),
            "fcf_growth": growth,
            "horizon_years": horizon,
        },
        "sensitivity_grid": grid,
    }
