"""Free cash flow and its derivatives. Specified by docs/data-model.md.

FCF = op_cash_flow - capex, with capex POSITIVE meaning cash spent (CLAUDE.md
sign conventions). P1 normalizes the sign, so nothing here has to guess.

`fcf_conversion` (FCF / net income) is the quiet one: a company whose reported
profit stops turning into cash is usually the first sign of an accounting
problem, well before anything shows up in the income statement.

For a bank, insurer, broker or REIT every number in this module is
`not_applicable`: "operating cash flow less capital expenditure" is not a
description of that balance sheet, and a null with no explanation would read as
missing data (P1 -> P2, 2026-09-19).
"""

from __future__ import annotations

from calc.facts import Ledger, missing_reason, nums, present
from calc.value import add, div, sub

BANK_REASON = (
    "not applicable to a bank, insurer, broker or REIT: operating cash flow less "
    "capex does not describe this balance sheet, and this filer reports no capex line"
)
EBITDA_BANK_REASON = (
    "not applicable to a bank, insurer, broker or REIT: this filer presents no "
    "operating income, so EBITDA cannot be built from it"
)


def free_cash_flow(ledger: Ledger, period: str, *, partial_scope: bool = False) -> dict:
    """op_cash_flow - capex for one period."""
    inputs = {
        "op_cash_flow": ledger.ref(period, "op_cash_flow"),
        "capex": ledger.ref(period, "capex"),
    }
    values = nums(inputs)
    return ledger.emit(
        None if partial_scope else sub(values["op_cash_flow"], values["capex"]),
        metric="fcf",
        period=period,
        unit="usd",
        formula="op_cash_flow - capex",
        inputs=present(inputs),
        paths=[f"financials.{period}.op_cash_flow", f"financials.{period}.capex"],
        reason=BANK_REASON if partial_scope else missing_reason(inputs, period),
        not_applicable=partial_scope,
    )


def fcf_conversion(ledger: Ledger, period: str, fcf: dict) -> dict:
    """FCF / net income. Below config.FCF_CONVERSION_FLAG raises a quality flag."""
    fcf_ref = ledger.derived_ref(fcf, "fcf")
    inputs = {"fcf": fcf_ref, "net_income": ledger.ref(period, "net_income")}
    values = nums(inputs)
    return ledger.emit(
        div(values["fcf"], values["net_income"]),
        metric="fcf_conversion",
        period=period,
        unit="fraction",
        formula="fcf / net_income",
        inputs=present(inputs),
        paths=["cash_flow.fcf", f"financials.{period}.net_income"],
        reason=_inherit(fcf, missing_reason(inputs, period)),
        not_applicable=_na(fcf),
    )


def fcf_yield(ledger: Ledger, period: str, fcf: dict) -> dict:
    """FCF / market cap. The valuation metric least sensitive to accounting choices."""
    inputs = {"fcf": ledger.derived_ref(fcf, "fcf"), "market_cap": ledger.market_ref("market_cap")}
    values = nums(inputs)
    return ledger.emit(
        div(values["fcf"], values["market_cap"]),
        metric="fcf_yield",
        period=period,
        unit="fraction",
        formula="fcf / market_cap",
        inputs=present(inputs),
        paths=["cash_flow.fcf", "market.market_cap"],
        reason=_inherit(fcf, missing_reason(inputs, period)),
        not_applicable=_na(fcf),
    )


def capex_intensity(ledger: Ledger, period: str, *, partial_scope: bool = False) -> dict:
    """Capex / revenue. How much growth has to be bought."""
    inputs = {"capex": ledger.ref(period, "capex"), "revenue": ledger.ref(period, "revenue")}
    values = nums(inputs)
    return ledger.emit(
        None if partial_scope else div(values["capex"], values["revenue"]),
        metric="capex_intensity",
        period=period,
        unit="fraction",
        formula="capex / revenue",
        inputs=present(inputs),
        paths=[f"financials.{period}.capex", f"financials.{period}.revenue"],
        reason=BANK_REASON if partial_scope else missing_reason(inputs, period),
        not_applicable=partial_scope,
    )


def ebitda(ledger: Ledger, period: str, *, partial_scope: bool = False) -> dict:
    """Operating income + D&A, UNADJUSTED.

    Deliberately not "adjusted EBITDA": every company adjusts differently, and
    an adjusted figure presented as a standard one is exactly what
    IssueType.ADJUSTED_AS_GAAP exists to catch.
    """
    inputs = {
        "operating_income": ledger.ref(period, "operating_income"),
        "depreciation_amortization": ledger.ref(period, "depreciation_amortization"),
    }
    values = nums(inputs)
    return ledger.emit(
        None
        if partial_scope
        else add(values["operating_income"], values["depreciation_amortization"]),
        metric="ebitda",
        period=period,
        unit="usd",
        formula="operating_income + depreciation_amortization",
        inputs=present(inputs),
        paths=[
            f"financials.{period}.operating_income",
            f"financials.{period}.depreciation_amortization",
        ],
        reason=EBITDA_BANK_REASON if partial_scope else missing_reason(inputs, period),
        not_applicable=partial_scope,
    )


def _na(vo: dict) -> bool:
    return bool(vo.get("not_applicable"))


def _inherit(vo: dict, fallback: str) -> str:
    """A metric built on a not-applicable input is not applicable for the same reason."""
    return vo.get("unavailable_reason") or fallback if _na(vo) else fallback
