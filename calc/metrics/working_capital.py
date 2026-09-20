"""Working-capital quality: receivables, inventory, and the balance sheet.

Specified by docs/data-model.md.

Receivables growing faster than revenue is the classic early warning: it can
mean longer payment terms granted to close deals, or revenue recognised before
cash is likely to arrive. Either way it is visible in the numbers a quarter or
two before it is visible in earnings, which is why it is computed rather than
left to prose.

Balance-sheet metrics use the LATEST REPORTED BALANCE SHEET, which may be a
quarter, while flow metrics use the latest full year. The two period choices are
named separately in `Metrics` because mixing them is a classic silent error.
"""

from __future__ import annotations

from calc import config
from calc.facts import Ledger, missing_reason, nums, present
from calc.value import div, sub

DAYS_PER_YEAR = 365.0

NO_INTEREST_REASON = (
    "interest_expense is not tagged by this filer (Apple nets it inside other "
    "income), so coverage would divide by nothing; a 0 here would read as distress"
)


def days_sales_outstanding(ledger: Ledger, period: str) -> dict:
    """receivables / revenue * 365."""
    inputs = {
        "receivables": ledger.ref(period, "receivables"),
        "revenue": ledger.ref(period, "revenue"),
    }
    values = nums(inputs)
    ratio = div(values["receivables"], values["revenue"])
    return ledger.emit(
        None if ratio is None else ratio * DAYS_PER_YEAR,
        metric="days_sales_outstanding",
        period=period,
        unit="days",
        formula=f"receivables / revenue * {DAYS_PER_YEAR}",
        inputs=present(inputs),
        paths=[f"financials.{period}.receivables", f"financials.{period}.revenue"],
        reason=missing_reason(inputs, period),
    )


def days_inventory(ledger: Ledger, period: str) -> dict:
    """inventory / cost_of_revenue * 365."""
    inputs = {
        "inventory": ledger.ref(period, "inventory"),
        "cost_of_revenue": ledger.ref(period, "cost_of_revenue"),
    }
    values = nums(inputs)
    ratio = div(values["inventory"], values["cost_of_revenue"])
    return ledger.emit(
        None if ratio is None else ratio * DAYS_PER_YEAR,
        metric="days_inventory",
        period=period,
        unit="days",
        formula=f"inventory / cost_of_revenue * {DAYS_PER_YEAR}",
        inputs=present(inputs),
        paths=[f"financials.{period}.inventory", f"financials.{period}.cost_of_revenue"],
        reason=missing_reason(inputs, period),
    )


def balance_sheet_metrics(ledger: Ledger, annual: str, balance: str, ebitda: dict) -> dict:
    """Net debt, leverage, interest coverage and the current ratio."""
    debt_inputs = {
        "total_debt": ledger.ref(balance, "total_debt"),
        "cash": ledger.ref(balance, "cash"),
    }
    values = nums(debt_inputs)
    net_debt = ledger.emit(
        sub(values["total_debt"], values["cash"]),
        metric="net_debt",
        period=balance,
        unit="usd",
        formula="total_debt - cash",
        inputs=present(debt_inputs),
        paths=[f"financials.{balance}.total_debt", f"financials.{balance}.cash"],
        period_type="instant",
        reason=missing_reason(debt_inputs, balance),
    )

    lev_inputs = {
        "net_debt": ledger.derived_ref(net_debt, "net_debt"),
        "ebitda": ledger.derived_ref(ebitda, "ebitda"),
    }
    values = nums(lev_inputs)
    net_debt_to_ebitda = ledger.emit(
        div(values["net_debt"], values["ebitda"]),
        metric="net_debt_to_ebitda",
        period=balance,
        unit="multiple",
        formula="net_debt / ebitda",
        inputs=present(lev_inputs),
        paths=["balance_sheet.net_debt", "cash_flow.ebitda"],
        period_type="instant",
        reason=(
            ebitda.get("unavailable_reason")
            if ebitda.get("not_applicable")
            else missing_reason(lev_inputs, balance)
        ),
        not_applicable=bool(ebitda.get("not_applicable")),
    )

    cover_inputs = {
        "operating_income": ledger.ref(annual, "operating_income"),
        "interest_expense": ledger.ref(annual, "interest_expense"),
    }
    values = nums(cover_inputs)
    interest_coverage = ledger.emit(
        div(values["operating_income"], values["interest_expense"]),
        metric="interest_coverage",
        period=annual,
        unit="multiple",
        formula="operating_income / interest_expense",
        inputs=present(cover_inputs),
        paths=[
            f"financials.{annual}.operating_income",
            f"financials.{annual}.interest_expense",
        ],
        reason=(
            NO_INTEREST_REASON
            if cover_inputs["interest_expense"] is None
            else missing_reason(cover_inputs, annual)
        ),
    )

    ratio_inputs = {
        "current_assets": ledger.ref(balance, "current_assets"),
        "current_liabilities": ledger.ref(balance, "current_liabilities"),
    }
    values = nums(ratio_inputs)
    current_ratio = ledger.emit(
        div(values["current_assets"], values["current_liabilities"]),
        metric="current_ratio",
        period=balance,
        unit="ratio",
        formula="current_assets / current_liabilities",
        inputs=present(ratio_inputs),
        paths=[
            f"financials.{balance}.current_assets",
            f"financials.{balance}.current_liabilities",
        ],
        period_type="instant",
        reason=missing_reason(ratio_inputs, balance),
    )

    return {
        "net_debt": net_debt,
        "net_debt_to_ebitda": net_debt_to_ebitda,
        "interest_coverage": interest_coverage,
        "current_ratio": current_ratio,
    }


# --------------------------------------------------------------------------
# Quality flags
# --------------------------------------------------------------------------
SEVERITY_TOLERANCE = 1e-9
"""Float slack at a band edge. A DSO ratio of exactly 1.05 computes as
1.0499999999999998, and a flag that fires on one machine and not another is
worse than either answer."""


def _severity(magnitude: float, threshold: float) -> str | None:
    """low / medium / high off one threshold and the shared severity ladder."""
    low, medium, high = config.FLAG_SEVERITY_STEPS
    magnitude += SEVERITY_TOLERANCE
    if magnitude < threshold * low:
        return None
    if magnitude < threshold * medium:
        return "low"
    if magnitude < threshold * high:
        return "medium"
    return "high"


def quality_flags(
    ledger: Ledger,
    annual: str,
    prior_annual: str | None,
    *,
    dilution: dict,
    eps_growth: dict,
    fcf_conversion: dict,
    sbc_pct_revenue: dict,
) -> list[dict]:
    """Deterministic earnings-quality warnings, against config.py thresholds.

    Each flag states what was observed with its numbers, so a reader can judge it
    rather than trusting the label. Nothing here is fatal and nothing here is an
    opinion: an agent may disagree with a flag in prose, but it cannot remove it.
    """
    flags: list[dict] = []

    if prior_annual:
        for flag, label, threshold, fn in (
            (
                "dso_rising",
                "Days sales outstanding",
                config.DSO_INCREASE_FLAG,
                days_sales_outstanding,
            ),
            (
                "inventory_days_rising",
                "Days inventory outstanding",
                config.INVENTORY_DAYS_FLAG,
                days_inventory,
            ),
        ):
            now = fn(ledger, annual).get("value")
            before = fn(ledger, prior_annual).get("value")
            if now is None or not before:
                continue
            change = now / before - 1
            severity = _severity(abs(change), threshold)
            if severity and change > 0:
                detail = (
                    f"{label} rose from {before:.1f} to {now:.1f} days ({prior_annual} to {annual})"
                )
                if flag == "dso_rising":
                    detail += ": receivables grew faster than revenue."
                else:
                    detail += "."
                flags.append({"flag": flag, "detail": detail, "severity": severity})

    shrink = dilution.get("value")
    eps = eps_growth.get("value")
    if shrink is not None and shrink < 0 and eps is not None and eps > 0:
        severity = _severity(abs(shrink), config.BUYBACK_FLAG)
        if severity:
            flags.append(
                {
                    "flag": "buyback_flatters_eps",
                    "detail": (
                        f"Diluted share count fell {abs(shrink) * 100:.1f}%, adding roughly "
                        f"{abs(shrink) * 100:.1f} points to the {eps * 100:.1f}% EPS growth."
                    ),
                    "severity": severity,
                }
            )

    conversion = fcf_conversion.get("value")
    if conversion is not None and conversion < config.FCF_CONVERSION_FLAG:
        flags.append(
            {
                "flag": "fcf_below_net_income",
                "detail": (
                    f"Free cash flow was {conversion * 100:.0f}% of net income in {annual}, below "
                    f"the {config.FCF_CONVERSION_FLAG * 100:.0f}% threshold: reported profit is "
                    "not turning into cash."
                ),
                "severity": _severity(config.FCF_CONVERSION_FLAG - conversion, 0.10) or "low",
            }
        )

    sbc = sbc_pct_revenue.get("value")
    if sbc is not None and sbc > config.SBC_REVENUE_FLAG:
        flags.append(
            {
                "flag": "sbc_heavy",
                "detail": (
                    f"Stock compensation was {sbc * 100:.1f}% of {annual} revenue, above the "
                    f"{config.SBC_REVENUE_FLAG * 100:.0f}% threshold."
                ),
                "severity": _severity(sbc - config.SBC_REVENUE_FLAG, config.SBC_REVENUE_FLAG)
                or "low",
            }
        )

    for gap in (ledger.factsheet.get("data_quality") or {}).get("gaps", []):
        if "restated from" in gap.lower():
            flags.append({"flag": "restated_prior_period", "detail": gap, "severity": "low"})

    return flags
