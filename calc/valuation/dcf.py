"""Discounted cash flow. Specified by docs/data-model.md and docs/adr/0001.

Every output is dominated by its assumptions, so every output ships with a
sensitivity grid. A single headline number would imply a precision this method
does not have (error D).

Three choices carry the model, and all three are recorded rather than buried:

**The base is an average, not a year.** `config.DCF_FCF_BASE_YEARS` (3) fiscal
years of FCF, averaged. Coca-Cola's FY2024 IRS deposit cut its reported FCF
nearly in half; a single-year base turns one payment into a permanent impairment
of the company, and then compounds it for a decade.

**The growth rate is the trailing REVENUE CAGR, bounded.** Revenue rather than
FCF because it is the least manipulable line and the least distorted by one-offs
- the same KO deposit makes its FCF CAGR -17%/yr while revenue grew 5.5%/yr.
Bounded into `[TERMINAL_GROWTH, DCF_MAX_ASSUMED_GROWTH]`: NVDA's 68%/yr is
clamped to 15%, and a negative CAGR is floored, because a decade of projected
decline off one trailing window values the window rather than the company.

**Growth fades.** Year 1 grows at the assumed rate, year N at the terminal rate,
interpolating linearly. A flat decade followed by a step down to 3% is the
standard shape and the wrong one: nothing decelerates like that.
"""

from __future__ import annotations

from calc import config
from calc.facts import Ledger, present
from calc.lineage import assumption_value
from calc.valuation.reverse_dcf import NON_ARITHMETIC, present_value, solve_implied_growth
from calc.value import div, value

NO_FCF = "no positive free cash flow to discount, so a DCF would be a projection of nothing"


# --------------------------------------------------------------------------
# The base
# --------------------------------------------------------------------------
def fcf_base(ledger: Ledger, latest: dict) -> dict:
    """The average FCF of the last `config.DCF_FCF_BASE_YEARS` full years.

    Falls back to however many years exist, with `years_used` recorded either way
    so a reader can see whether the base was smoothed or not, and
    `latest_vs_average` so they can see how much the smoothing mattered.
    """
    annuals = [label for label in ledger.periods if label.startswith("FY")]
    wanted = annuals[: config.DCF_FCF_BASE_YEARS]
    inputs: dict = {}
    values: list[float] = []
    used: list[str] = []
    for label in wanted:
        ocf = ledger.ref(label, "op_cash_flow")
        capex = ledger.ref(label, "capex")
        if ocf is None or capex is None:
            continue
        key = label.replace("-", "_")
        inputs[f"op_cash_flow_{key}"] = ocf
        inputs[f"capex_{key}"] = capex
        values.append(ocf.value - capex.value)
        used.append(label)

    if not values:
        out = dict(latest)
        out["years_used"] = []
        out["basis"] = "unavailable"
        return out

    formula = " + ".join(
        f"(op_cash_flow_{label.replace('-', '_')} - capex_{label.replace('-', '_')})"
        for label in used
    )
    out = ledger.emit(
        sum(values) / len(values),
        metric=f"fcf_average_{len(used)}y",
        period=used[0],
        unit="usd",
        formula=f"({formula}) / {len(used)}",
        inputs=inputs,
        paths=[f"financials.{label}.op_cash_flow" for label in used]
        + [f"financials.{label}.capex" for label in used],
        reason=latest.get("unavailable_reason") or "no full year has both cash flow and capex",
        not_applicable=bool(latest.get("not_applicable")),
    )
    out["years_used"] = used
    out["basis"] = f"{len(used)}-year average"
    out["latest_year"] = latest.get("value")
    if latest.get("value") and out.get("value"):
        out["latest_vs_average"] = round(latest["value"] / out["value"] - 1, 10)

    # An average of DOLLARS smooths a one-off and also flattens real growth: for
    # NVDA, whose FCF went 27bn -> 61bn -> 97bn, the three-year average is 36%
    # below the current run-rate, which is not a normalised base but a stale one.
    # Averaging the MARGIN and applying it to the latest year's revenue smooths the
    # same one-off while keeping today's scale. It is reported, not used: switching
    # the base is the caller's call, and both numbers are here to make it.
    margins: list[float] = []
    for label in used:
        ocf = ledger.ref(label, "op_cash_flow")
        capex = ledger.ref(label, "capex")
        revenue = ledger.ref(label, "revenue")
        if ocf is None or capex is None or revenue is None or not revenue.value:
            continue
        margins.append((ocf.value - capex.value) / revenue.value)
    latest_revenue = ledger.ref(used[0], "revenue")
    if margins and latest_revenue is not None:
        alternative = sum(margins) / len(margins) * latest_revenue.value
        out["margin_based_alternative"] = round(alternative, 10)
        out["average_fcf_margin"] = round(sum(margins) / len(margins), 10)
        out["alternative_note"] = (
            f"the average FCF MARGIN over {', '.join(used)} applied to {used[0]} revenue is "
            f"{alternative:,.0f} USD, against the dollar average of {out['value']:,.0f}. "
            "Where the two disagree sharply the company's scale changed over the window."
        )
    return out


# --------------------------------------------------------------------------
# The growth rate
# --------------------------------------------------------------------------
def growth_input(ledger: Ledger, metrics: dict) -> dict:
    """The assumed year-one growth rate, bounded, with both bounds recorded."""
    cagr = (metrics.get("cagr") or {}).get("revenue") or {}
    requested = cagr.get("value")
    cap = config.DCF_MAX_ASSUMED_GROWTH
    floor = config.TERMINAL_GROWTH
    clamped = floored = False

    if requested is None:
        applied = floor
        source = "config"
        note = (
            "no trailing revenue CAGR was computable, so the explicit period grows at the "
            "terminal rate - a deliberately unambitious default"
        )
    else:
        applied = requested
        if applied > cap:
            applied, clamped = cap, True
        elif applied < floor:
            applied, floored = floor, True
        source = "trailing_revenue_cagr"
        if clamped:
            note = (
                f"trailing revenue CAGR of {requested:.1%}/yr exceeds the {cap:.0%} cap on an "
                f"assumed growth rate and was clamped to {applied:.0%}"
            )
        elif floored:
            note = (
                f"trailing revenue CAGR of {requested:.1%}/yr is below the terminal rate, so "
                f"the floor of {applied:.0%} applies: a decade of projected decline off one "
                "trailing window values the window, not the company"
            )
        else:
            note = f"trailing revenue CAGR of {requested:.1%}/yr, inside [{floor:.0%}, {cap:.0%}]"

    out = assumption_value(applied, "fraction", config.CONFIG_SOURCE)
    out["requested"] = requested
    out["cap"] = cap
    out["floor"] = floor
    out["was_clamped"] = clamped
    out["was_floored"] = floored
    out["basis"] = source
    out["fades_to"] = config.TERMINAL_GROWTH
    out["note"] = note
    if config.DCF_GROWTH_FADE:
        out["fade"] = (
            f"year 1 grows at {applied:.1%} and year {config.DCF_HORIZON_YEARS} at "
            f"{config.TERMINAL_GROWTH:.1%}, interpolating linearly"
        )
    return out


def growth_schedule(g0: float, terminal: float, years: int) -> list[float]:
    """The per-year growth rates: g0 in year 1, `terminal` in year N."""
    if years <= 1 or not config.DCF_GROWTH_FADE:
        return [g0] * max(years, 1)
    step = (terminal - g0) / (years - 1)
    return [g0 + step * index for index in range(years)]


def present_value_fading(
    fcf0: float | None,
    g0: float,
    discount_rate: float,
    terminal_growth: float,
    years: int,
) -> float | None:
    """PV of an FCF stream whose growth fades to the terminal rate, plus the TV."""
    if fcf0 is None or fcf0 <= 0 or discount_rate <= terminal_growth or discount_rate <= 0:
        return None
    total = 0.0
    fcf = fcf0
    for index, growth in enumerate(growth_schedule(g0, terminal_growth, years), start=1):
        fcf *= 1 + growth
        total += fcf / (1 + discount_rate) ** index
    terminal = fcf * (1 + terminal_growth) / (discount_rate - terminal_growth)
    return total + terminal / (1 + discount_rate) ** years


# --------------------------------------------------------------------------
# The valuation
# --------------------------------------------------------------------------
def simple_dcf(ledger: Ledger, metrics: dict, assumptions: dict | None = None) -> dict:
    """A forward DCF on the same config the reverse DCF uses.

    Enterprise value, then equity value after net debt, then a per-share value and
    the upside to today's price. Every cell of the grid is a full valuation, not a
    single-axis sensitivity.
    """
    assumptions = assumptions or {}
    discount_rate = float(assumptions.get("discount_rate", config.DISCOUNT_RATE))
    terminal_growth = float(assumptions.get("terminal_growth", config.TERMINAL_GROWTH))
    horizon = int(assumptions.get("horizon_years", config.DCF_HORIZON_YEARS))

    base = metrics["cash_flow"].get("fcf_base") or fcf_base(ledger, metrics["cash_flow"]["fcf"])
    base_ref = ledger.derived_ref(base, "fcf_average")
    fcf = base.get("value")
    growth = growth_input(ledger, metrics)
    if assumptions.get("fcf_growth") is not None:
        override = float(assumptions["fcf_growth"])
        growth = assumption_value(override, "fraction", config.CONFIG_SOURCE)
        growth.update(
            {
                "basis": "caller_override",
                "requested": override,
                "cap": config.DCF_MAX_ASSUMED_GROWTH,
                "floor": terminal_growth,
                "was_clamped": False,
                "was_floored": False,
                "fades_to": terminal_growth,
                "note": "growth rate supplied by the caller's assumptions",
            }
        )

    period = metrics["latest_annual_period"]
    balance = metrics["latest_balance_period"]

    reason = None
    if base.get("not_applicable"):
        reason = base.get("unavailable_reason")
    elif fcf is None or fcf <= 0:
        reason = base.get("unavailable_reason") or NO_FCF

    debt_ref = ledger.ref(balance, "total_debt")
    cash_ref = ledger.ref(balance, "cash")
    shares_ref = ledger.market_ref("shares_outstanding") or ledger.ref(period, "shares_diluted")
    price = ledger.market_ref("price")

    def valuation_at(rate: float, tg: float, metric: str) -> dict:
        ev = None if reason else present_value_fading(fcf, growth["value"], rate, tg, horizon)
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
                f"{equity:,.0f} USD at r={rate:.0%}, g={growth['value']:.1%} fading to "
                f"{tg:.0%}), so this model produces no per-share value for this company"
            )
            equity = None
        per_share = div(equity, shares_ref.value if shares_ref else None)
        return ledger.emit(
            per_share,
            metric=metric,
            period=period,
            unit="usd_per_share",
            formula=(
                f"(pv(fcf_base, g={growth['value']} fading to {tg}, r={rate}, n={horizon}) "
                "- (total_debt - cash)) / shares_outstanding"
            ),
            inputs=present(
                {
                    "fcf_base": base_ref,
                    "total_debt": debt_ref,
                    "cash": cash_ref,
                    "shares_outstanding": shares_ref,
                }
            ),
            paths=[
                "valuation.dcf.fcf_base",
                f"financials.{balance}.total_debt",
                f"financials.{balance}.cash",
                "market.shares_outstanding",
            ],
            period_type="instant",
            value_type="estimate",
            reason=why
            or "net debt or the share count is unavailable, so no per-share value can be built",
            not_applicable=bool(base.get("not_applicable")),
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
        "fcf_base": base,
        "assumptions": {
            "discount_rate": assumption_value(discount_rate, "fraction", config.CONFIG_SOURCE),
            "terminal_growth": assumption_value(terminal_growth, "fraction", config.CONFIG_SOURCE),
            "fcf_growth": growth,
            "horizon_years": horizon,
            "growth_schedule": [
                round(rate, 10)
                for rate in growth_schedule(growth["value"], terminal_growth, horizon)
            ],
            "rates_are_nominal": True,
        },
        "sensitivity_grid": grid,
    }


def sensitivity_grid(fcf0: float, target_value: float, years: int) -> list[dict]:
    """Solve across the config.py discount-rate and terminal-growth axes.

    The spread across this grid is the honest answer; the centre cell alone is not.
    Kept as the documented entry point for a caller holding a target value rather
    than a ledger.
    """
    return [
        {
            "discount_rate": rate,
            "terminal_growth": tg,
            "implied_fcf_cagr": value(
                solve_implied_growth(target_value, fcf0, rate, tg, years),
                "fraction",
                "fact",
                derived_from=["market.enterprise_value", "valuation.dcf.fcf_base"],
                reason="the discounted cash flow identity has no solution for these inputs",
            ),
        }
        for rate in config.SENSITIVITY_DISCOUNT_RATES
        for tg in config.SENSITIVITY_TERMINAL_GROWTHS
    ]


__all__ = [
    "fcf_base",
    "growth_input",
    "growth_schedule",
    "present_value",
    "present_value_fading",
    "sensitivity_grid",
    "simple_dcf",
]
