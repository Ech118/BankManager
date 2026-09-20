"""Assemble one `Metrics` object from one `Factsheet`. The Step 1 entry point.

`calc.api.compute_metrics` is a one-line delegate to `compute_metrics` here.

What this function guarantees, and what audit/ relies on:

- **every leaf is a ValueObject**, `fact` or `estimate` or `assumption`, with the
  dotted paths it came from;
- **every available leaf is also a derived FinancialFact** in
  `metrics["derived_facts"]`, carrying the formula, its input fact_ids and a
  `filed_at` equal to the latest of those inputs;
- **a missing input yields `unavailable` with a reason**, never 0 and never an
  exception;
- **a bank, insurer, broker or REIT** gets `not_applicable` on the metrics that
  do not describe it, and book value per share and ROE where the data exists.

Two extra top-level keys ride along beside the contract's fields, which tolerate
them (`extra="allow"`): `derived_facts` / `input_facts` for the verifier, and
`cagr` / `returns` / `notes` for the report.
"""

from __future__ import annotations

from calc.facts import Ledger, is_partial_scope
from calc.metrics import fcf as fcf_mod
from calc.metrics import growth as growth_mod
from calc.metrics import margins as margins_mod
from calc.metrics import sbc_dilution, working_capital
from calc.valuation.dcf import fcf_base
from calc.valuation.multiples import multiples
from calc.valuation.reverse_dcf import reverse_dcf_block
from calc.value import unavailable


def compute_metrics(factsheet: dict, assumptions: dict | None = None) -> dict:
    """Factsheet -> Metrics. Pure: no network, no database, no LLM, no clock."""
    ledger = Ledger(factsheet)
    partial = is_partial_scope(factsheet)
    annual = ledger.latest_annual_label()
    balance = next(iter(ledger.periods), None)

    if annual is None:
        # Nothing to compute from: a quarterly-only history is not an error, it is
        # an empty answer with a reason attached.
        ledger.note("no full fiscal year on the factsheet, so no flow metric could be computed")
        annual = balance or ledger.as_of

    prior_annual = growth_mod.comparable_prior(ledger, annual) if annual in ledger.periods else None

    margins = margins_mod.all_margins(ledger, partial_scope=partial)
    growth = growth_mod.all_growth(ledger, partial_scope=partial)
    cagr = growth_mod.all_cagr(ledger)

    fcf = fcf_mod.free_cash_flow(ledger, annual, partial_scope=partial)
    ebitda = fcf_mod.ebitda(ledger, annual, partial_scope=partial)
    base = fcf_base(ledger, fcf)
    cash_flow = {
        "fcf": fcf,
        "fcf_base": base,
        "fcf_conversion": fcf_mod.fcf_conversion(ledger, annual, fcf),
        "fcf_yield": fcf_mod.fcf_yield(ledger, annual, fcf),
        "capex_intensity": fcf_mod.capex_intensity(ledger, annual, partial_scope=partial),
        "ebitda": ebitda,
    }

    balance_sheet = working_capital.balance_sheet_metrics(ledger, annual, balance or annual, ebitda)

    dilution = (
        sbc_dilution.dilution_yoy(ledger, annual, prior_annual)
        if prior_annual
        else unavailable("fraction", reason=f"no comparable prior year for {annual}")
    )
    per_share = {
        "dilution_yoy": dilution,
        "sbc_pct_revenue": sbc_dilution.sbc_pct_revenue(ledger, annual),
        "sbc_pct_fcf": sbc_dilution.sbc_pct_fcf(ledger, annual, fcf),
        "book_value_per_share": sbc_dilution.book_value_per_share(ledger, balance or annual),
    }

    eps_growth = (growth.get(annual) or {}).get("eps_yoy") or unavailable("fraction")
    quality_flags = working_capital.quality_flags(
        ledger,
        annual,
        prior_annual,
        dilution=dilution,
        eps_growth=eps_growth,
        fcf_conversion=cash_flow["fcf_conversion"],
        sbc_pct_revenue=per_share["sbc_pct_revenue"],
    )

    valuation = multiples(
        ledger,
        annual=annual,
        balance=balance or annual,
        ebitda=ebitda,
        fcf=fcf,
        partial_scope=partial,
    )
    reverse_dcf = reverse_dcf_block(
        ledger, fcf, period=annual, assumptions=assumptions, smoothed_base=base
    )

    if partial:
        ledger.note(
            "partial scope: free cash flow, gross margin and the enterprise-value "
            "multiples are reported not_applicable; book value per share, ROE and P/B "
            "carry the valuation instead"
        )

    return {
        "schema_version": factsheet["schema_version"],
        "ticker": factsheet["ticker"],
        "as_of": factsheet["as_of"],
        "latest_annual_period": annual,
        "latest_balance_period": balance or annual,
        "margins": margins,
        "growth": growth,
        "cash_flow": cash_flow,
        "balance_sheet": balance_sheet,
        "per_share": per_share,
        "quality_flags": quality_flags,
        "valuation": valuation,
        "reverse_dcf": reverse_dcf,
        # ---- additive, outside the contract's required fields ----
        "cagr": cagr,
        "returns": {"roe": sbc_dilution.return_on_equity(ledger, annual)},
        "scope_level": "partial" if partial else "supported",
        "derived_facts": ledger.derived_facts,
        "input_facts": ledger.input_facts,
        "notes": ledger.notes,
    }
