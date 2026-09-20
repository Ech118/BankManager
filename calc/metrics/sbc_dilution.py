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

from calc.facts import Ledger, missing_reason, nums, present
from calc.metrics.growth import per_share_inputs
from calc.value import div, ratio_minus_one


def dilution_yoy(ledger: Ledger, period: str, prior: str) -> dict:
    """Change in diluted share count. Negative means buybacks shrank it.

    Uses the split-adjusted share count when P1 published one, and is unavailable
    across an unadjusted share-basis break: a 10-for-1 split is not 900% dilution.
    """
    inputs, blocked = per_share_inputs(ledger, "shares_diluted", period, prior)
    names = list(inputs)
    values = nums(inputs)
    return ledger.emit(
        None
        if blocked
        else ratio_minus_one(values[names[0]], values[names[1]])
        if inputs
        else None,
        metric="dilution_yoy",
        period=period,
        unit="fraction",
        formula=(f"{names[0]} / {names[1]} - 1" if inputs else "shares / prior_shares - 1"),
        inputs=present(inputs),
        paths=[f"financials.{period}.shares_diluted", f"financials.{prior}.shares_diluted"],
        reason=blocked or missing_reason(inputs, f"{prior} to {period}"),
    )


def sbc_pct_revenue(ledger: Ledger, period: str) -> dict:
    """SBC / revenue. Above config.SBC_REVENUE_FLAG raises a quality flag."""
    inputs = {"sbc": ledger.ref(period, "sbc"), "revenue": ledger.ref(period, "revenue")}
    values = nums(inputs)
    return ledger.emit(
        div(values["sbc"], values["revenue"]),
        metric="sbc_pct_revenue",
        period=period,
        unit="fraction",
        formula="sbc / revenue",
        inputs=present(inputs),
        paths=[f"financials.{period}.sbc", f"financials.{period}.revenue"],
        reason=missing_reason(inputs, period),
    )


def sbc_pct_fcf(ledger: Ledger, period: str, fcf: dict) -> dict:
    """SBC / FCF. The harsher framing: what share of cash generation is paid in stock."""
    inputs = {"sbc": ledger.ref(period, "sbc"), "fcf": ledger.derived_ref(fcf, "fcf")}
    values = nums(inputs)
    return ledger.emit(
        div(values["sbc"], values["fcf"]),
        metric="sbc_pct_fcf",
        period=period,
        unit="fraction",
        formula="sbc / fcf",
        inputs=present(inputs),
        paths=[f"financials.{period}.sbc", "cash_flow.fcf"],
        reason=(
            fcf.get("unavailable_reason")
            if fcf.get("not_applicable")
            else missing_reason(inputs, period)
        ),
        not_applicable=bool(fcf.get("not_applicable")),
    )


def book_value_per_share(ledger: Ledger, period: str) -> dict:
    """Total equity / diluted shares. The metric that does describe a bank.

    Computed for every filer, not just financials: it is the denominator of P/B,
    which is how a bank or insurer is actually valued (P1 -> P2, 2026-09-19).
    """
    inputs = {
        "total_equity": ledger.ref(period, "total_equity"),
        "shares_diluted": ledger.ref(period, "shares_diluted"),
    }
    values = nums(inputs)
    return ledger.emit(
        div(values["total_equity"], values["shares_diluted"]),
        metric="book_value_per_share",
        period=period,
        unit="usd_per_share",
        formula="total_equity / shares_diluted",
        inputs=present(inputs),
        paths=[f"financials.{period}.total_equity", f"financials.{period}.shares_diluted"],
        reason=missing_reason(inputs, period),
    )


def return_on_equity(ledger: Ledger, period: str) -> dict:
    """Net income / total equity. Available wherever both are reported.

    Not averaged over opening and closing equity: the factsheet carries one
    balance sheet per period, and an average that silently mixes two filings is
    worse than a stated point-in-time ratio.
    """
    inputs = {
        "net_income": ledger.ref(period, "net_income"),
        "total_equity": ledger.ref(period, "total_equity"),
    }
    values = nums(inputs)
    return ledger.emit(
        div(values["net_income"], values["total_equity"]),
        metric="roe",
        period=period,
        unit="fraction",
        formula="net_income / total_equity",
        inputs=present(inputs),
        paths=[f"financials.{period}.net_income", f"financials.{period}.total_equity"],
        reason=missing_reason(inputs, period),
    )


def eps_growth_attribution(ledger: Ledger, period: str, prior: str) -> dict:
    """Split EPS growth into the part from earnings and the part from buybacks.

    Computed here rather than asserted by an agent: the mock audit fixture
    carries a warning about exactly this number being rounded by an agent
    instead of recomputed.
    """
    net_growth = ratio_minus_one(
        _num(ledger.ref(period, "net_income")), _num(ledger.ref(prior, "net_income"))
    )
    share_change = ratio_minus_one(
        _num(ledger.ref(period, "shares_diluted")), _num(ledger.ref(prior, "shares_diluted"))
    )
    eps_growth = ratio_minus_one(
        _num(ledger.ref(period, "eps_diluted")), _num(ledger.ref(prior, "eps_diluted"))
    )
    from_buyback = None
    if eps_growth is not None and net_growth is not None:
        from_buyback = eps_growth - net_growth
    return {
        "period": period,
        "prior": prior,
        "eps_growth": eps_growth,
        "from_earnings": net_growth,
        "from_share_count": from_buyback,
        "share_count_change": share_change,
    }


def _num(ref) -> float | None:
    return None if ref is None else ref.value
