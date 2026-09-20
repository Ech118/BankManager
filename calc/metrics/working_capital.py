"""Working-capital quality: receivables, inventory, and the balance sheet.

Specified by docs/data-model.md.

Receivables growing faster than revenue is the classic early warning: it can
mean longer payment terms granted to close deals, or revenue recognised before
cash is likely to arrive. Either way it is visible in the numbers a quarter or
two before it is visible in earnings, which is why it is computed rather than
left to prose.
"""

from __future__ import annotations

import re

from calc import config
from calc._util import div, num, ratio_minus_one
from calc.lineage import derived_value
from calc.metrics.fcf import ebitda, fcf_conversion
from calc.metrics.growth import comparable_prior
from calc.metrics.sbc_dilution import dilution_yoy, sbc_pct_revenue
from schema.contracts.common import ValueObject
from schema.contracts.enums import FlagSeverity
from schema.contracts.factsheet import Factsheet, FinancialPeriod
from schema.contracts.metrics import BalanceSheet, QualityFlag

DAYS_PER_YEAR = 365.0

_SOURCE_ACCESSION_RE = re.compile(r"^src:edgar:([^:]+):")

_FIELD_NAMES = [
    "revenue", "cost_of_revenue", "gross_profit", "operating_income", "pretax_income",
    "net_income", "eps_diluted", "shares_diluted", "depreciation_amortization",
    "op_cash_flow", "capex", "sbc", "cash", "total_debt", "interest_expense",
    "total_assets", "total_equity", "current_assets", "current_liabilities",
    "receivables", "inventory",
]


def days_sales_outstanding(factsheet: Factsheet, period: str) -> ValueObject:
    """receivables / revenue * 365."""
    p = factsheet.period(period)
    value = None
    if p is not None:
        ratio = div(num(p.receivables), num(p.revenue))
        value = None if ratio is None else ratio * DAYS_PER_YEAR
    return derived_value(value, "days",
                          [f"financials.{period}.receivables", f"financials.{period}.revenue"])


def days_inventory(factsheet: Factsheet, period: str) -> ValueObject:
    """inventory / cost_of_revenue * 365."""
    p = factsheet.period(period)
    value = None
    if p is not None:
        ratio = div(num(p.inventory), num(p.cost_of_revenue))
        value = None if ratio is None else ratio * DAYS_PER_YEAR
    return derived_value(value, "days",
                          [f"financials.{period}.inventory", f"financials.{period}.cost_of_revenue"])


def balance_sheet_metrics(factsheet: Factsheet) -> BalanceSheet:
    """Net debt, leverage, interest coverage and the current ratio.

    Uses the LATEST REPORTED BALANCE SHEET, which may be a quarter, while flow
    metrics use the latest full year.
    """
    balance_period = factsheet.latest_balance_period
    annual_period = factsheet.latest_annual_period
    bal = factsheet.period(balance_period)
    ann = factsheet.period(annual_period) if annual_period else None

    net_debt = None
    if bal is not None:
        net_debt = None if num(bal.total_debt) is None or num(bal.cash) is None else \
            num(bal.total_debt) - num(bal.cash)
    ebitda_annual = ebitda(factsheet, annual_period).value if annual_period else None

    return BalanceSheet(
        net_debt=derived_value(net_debt, "usd",
                                [f"financials.{balance_period}.total_debt",
                                 f"financials.{balance_period}.cash"]),
        net_debt_to_ebitda=derived_value(div(net_debt, ebitda_annual), "multiple",
                                          ["balance_sheet.net_debt", "cash_flow.ebitda"]),
        interest_coverage=derived_value(
            div(num(ann.operating_income), num(ann.interest_expense)) if ann else None,
            "multiple",
            [f"financials.{annual_period}.operating_income",
             f"financials.{annual_period}.interest_expense"] if annual_period else []),
        current_ratio=derived_value(
            div(num(bal.current_assets), num(bal.current_liabilities)) if bal else None,
            "ratio",
            [f"financials.{balance_period}.current_assets",
             f"financials.{balance_period}.current_liabilities"]),
    )


def _severity(pct: float, threshold: float) -> FlagSeverity:
    if pct >= 2 * threshold:
        return FlagSeverity.HIGH
    if pct >= threshold:
        return FlagSeverity.MEDIUM
    return FlagSeverity.LOW


def _restated_fields(period: FinancialPeriod) -> list[str]:
    """Fields whose source_id cites a LATER accession than the period's own
    filing - the signal that this figure was restated, purely from the
    Factsheet (no separate truth-layer lookup needed)."""
    restated = []
    for field in _FIELD_NAMES:
        vo = getattr(period, field)
        if vo.source_id:
            m = _SOURCE_ACCESSION_RE.match(vo.source_id)
            if m and m.group(1) != period.accession:
                restated.append(field)
    return restated


def quality_flags(factsheet: Factsheet) -> list[QualityFlag]:
    """Deterministic earnings-quality warnings, against config.py thresholds.

    Each flag states what was observed with its numbers, so a reader can judge
    it rather than trusting the label.
    """
    flags: list[QualityFlag] = []
    annual_period = factsheet.latest_annual_period

    if annual_period:
        prior = comparable_prior(factsheet, annual_period)
        if prior:
            dso_now = days_sales_outstanding(factsheet, annual_period).value
            dso_prev = days_sales_outstanding(factsheet, prior).value
            if dso_now is not None and dso_prev is not None and dso_prev > 0:
                pct = dso_now / dso_prev - 1
                if pct > 0:
                    flags.append(QualityFlag(
                        flag="dso_rising",
                        detail=f"Days sales outstanding rose from {dso_prev:.1f} to {dso_now:.1f} "
                               f"days ({prior} to {annual_period}): receivables grew faster than revenue.",
                        severity=_severity(pct, config.DSO_INCREASE_FLAG),
                    ))

            inv_now = days_inventory(factsheet, annual_period).value
            inv_prev = days_inventory(factsheet, prior).value
            if inv_now is not None and inv_prev is not None and inv_prev > 0:
                pct = inv_now / inv_prev - 1
                if pct > config.INVENTORY_DAYS_INCREASE_FLAG:
                    flags.append(QualityFlag(
                        flag="inventory_days_rising",
                        detail=f"Days inventory outstanding rose from {inv_prev:.1f} to {inv_now:.1f} "
                               f"days ({prior} to {annual_period}).",
                        severity=_severity(pct, config.INVENTORY_DAYS_INCREASE_FLAG),
                    ))

            dilution = dilution_yoy(factsheet, annual_period, prior).value
            eps_growth = None
            cur_p, prev_p = factsheet.period(annual_period), factsheet.period(prior)
            if cur_p and prev_p:
                eps_growth = ratio_minus_one(num(cur_p.eps_diluted), num(prev_p.eps_diluted))
            if dilution is not None and dilution < 0 and eps_growth is not None and eps_growth > 0:
                magnitude = abs(dilution)
                if magnitude > config.BUYBACK_DILUTION_FLAG:
                    flags.append(QualityFlag(
                        flag="buyback_flatters_eps",
                        detail=f"Diluted share count fell {magnitude * 100:.1f}%, adding roughly "
                               f"{magnitude * 100:.1f} points to the {eps_growth * 100:.1f}% EPS growth.",
                        severity=_severity(magnitude, config.BUYBACK_DILUTION_FLAG),
                    ))

        conversion = fcf_conversion(factsheet, annual_period).value
        if conversion is not None and conversion < config.FCF_CONVERSION_FLAG:
            flags.append(QualityFlag(
                flag="weak_fcf_conversion",
                detail=f"FCF / net income is {conversion:.2f} in {annual_period}, below the "
                       f"{config.FCF_CONVERSION_FLAG:.2f} watch level: reported profit is not "
                       "fully turning into cash.",
                severity=FlagSeverity.MEDIUM,
            ))

        sbc_pct = sbc_pct_revenue(factsheet, annual_period).value
        if sbc_pct is not None and sbc_pct > config.SBC_REVENUE_FLAG:
            flags.append(QualityFlag(
                flag="high_sbc",
                detail=f"Stock-based compensation is {sbc_pct * 100:.1f}% of revenue in "
                       f"{annual_period}, above the {config.SBC_REVENUE_FLAG * 100:.0f}% watch level.",
                severity=FlagSeverity.LOW,
            ))

    for p in factsheet.financials:
        restated = _restated_fields(p)
        if restated:
            flags.append(QualityFlag(
                flag="restated_prior_period",
                detail=f"{p.period} {', '.join(restated)} cite{'s' if len(restated) == 1 else ''} "
                       "a later filing than the period's own accession, indicating a restatement.",
                severity=FlagSeverity.LOW,
            ))

    return flags
