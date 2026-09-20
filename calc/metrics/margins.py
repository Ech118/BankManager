"""Margin computation. Specified by docs/data-model.md.

All margins are FRACTIONS (0.40 means 40%). The contract rejects anything above
10 for a fraction unit, so a percent that escapes conversion fails loudly rather
than travelling into the report.

Gross margin is the one that does not survive a change of industry: a bank
presents no cost of revenue, so for a partial-scope filer it is reported as
`not_applicable` rather than as a number that happens to be missing
(P1 -> P2, 2026-09-19).
"""

from __future__ import annotations

from calc.facts import Ledger, missing_reason, nums, present
from calc.value import div, sub

GROSS_BANK_REASON = (
    "not applicable to a bank, insurer, broker or REIT: this filer presents no cost "
    "of revenue, so a gross margin would be an artefact of the concept map"
)
FCF_BANK_REASON = (
    "not applicable to a bank, insurer, broker or REIT: operating cash flow less "
    "capex does not describe this balance sheet"
)


def margins_for(ledger: Ledger, period: str, *, partial_scope: bool = False) -> dict:
    """Gross, operating, net and FCF margin for one period."""
    out: dict[str, dict] = {}
    for name, metric, field in (
        ("gross", "gross_margin", "gross_profit"),
        ("operating", "operating_margin", "operating_income"),
        ("net", "net_margin", "net_income"),
    ):
        inputs = {field: ledger.ref(period, field), "revenue": ledger.ref(period, "revenue")}
        values = nums(inputs)
        blocked = partial_scope and name == "gross"
        out[name] = ledger.emit(
            None if blocked else div(values[field], values["revenue"]),
            metric=metric,
            period=period,
            unit="fraction",
            formula=f"{field} / revenue",
            inputs=present(inputs),
            paths=[f"financials.{period}.{field}", f"financials.{period}.revenue"],
            reason=GROSS_BANK_REASON if blocked else missing_reason(inputs, period),
            not_applicable=blocked,
        )

    inputs = {
        "op_cash_flow": ledger.ref(period, "op_cash_flow"),
        "capex": ledger.ref(period, "capex"),
        "revenue": ledger.ref(period, "revenue"),
    }
    values = nums(inputs)
    fcf = sub(values["op_cash_flow"], values["capex"])
    out["fcf"] = ledger.emit(
        None if partial_scope else div(fcf, values["revenue"]),
        metric="fcf_margin",
        period=period,
        unit="fraction",
        formula="(op_cash_flow - capex) / revenue",
        inputs=present(inputs),
        paths=[
            f"financials.{period}.op_cash_flow",
            f"financials.{period}.capex",
            f"financials.{period}.revenue",
        ],
        reason=FCF_BANK_REASON if partial_scope else missing_reason(inputs, period),
        not_applicable=partial_scope,
    )
    return out


def all_margins(ledger: Ledger, *, partial_scope: bool = False) -> dict[str, dict]:
    """Margins for every reported period, keyed by period label."""
    return {
        label: margins_for(ledger, label, partial_scope=partial_scope) for label in ledger.periods
    }
