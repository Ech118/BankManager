"""P2 (Calc, Audit & Eval) owns this file. Public interface of the math layer.

calc/ IS PURE (docs/adr/0001, docs/adr/0007):
  - no network, no database, no filesystem beyond the mock fixtures,
  - no LLM call, ever,
  - no `as_of` parameter where a factsheet is already supplied: the factsheet's
    own as_of is authoritative and a second one could silently disagree.

Everything an LLM proposes is BOUNDED here, and the bounding is recorded:
  - scenario weights are clamped into a band around the defaults (ScenarioWeights),
  - the prior shift is capped (Prior).

Signatures MUST NOT change (CONTRACT-CHANGE PR, CONTRIBUTING.md);
tests/contracts/test_signatures.py enforces this.
"""

from __future__ import annotations

from calc._util import div, num
from calc.lineage import derived_value
from calc.metrics.fcf import capex_intensity, ebitda, fcf_conversion, fcf_yield, free_cash_flow
from calc.metrics.growth import all_growth, comparable_prior
from calc.metrics.margins import all_margins
from calc.metrics.sbc_dilution import dilution_yoy, sbc_pct_fcf, sbc_pct_revenue
from calc.metrics.working_capital import balance_sheet_metrics, quality_flags
from calc.scenarios.consistency import validate_consistency as _validate_consistency
from calc.scenarios.evaluate import evaluate_scenarios as _evaluate_scenarios
from calc.scenarios.rubric import derive_scores as _derive_scores
from calc.valuation import peers as peers_mod
from calc.valuation.multiples import (
    ev_ebitda,
    ev_revenue,
    forward_pe,
    price_to_earnings,
    price_to_fcf,
)
from calc.valuation.reverse_dcf import reverse_dcf as _reverse_dcf
from schema.contracts.factsheet import Factsheet
from schema.contracts.metrics import CashFlow, Metrics, PerShare, Valuation, VsSP500
from schema.contracts.scenario_result import ScenarioResult
from schema.contracts.scenarios import PriorShift, Scenarios
from schema.contracts.verdict import VerdictCard


def _build_valuation(fs: Factsheet, ebitda_value: float | None, fcf_value: float | None) -> Valuation:
    annual = fs.latest_annual_period
    pe = price_to_earnings(fs, annual) if annual else derived_value(None, "multiple", [])
    fpe = forward_pe(fs)
    eve = ev_ebitda(fs, ebitda_value)
    evr = ev_revenue(fs, annual) if annual else derived_value(None, "multiple", [])
    pfcf = price_to_fcf(fs, fcf_value)
    vs_peers = peers_mod.compare({"pe": pe.value, "ev_ebitda": eve.value}, fs.peers)

    sp500_fwd_pe = num(fs.sp500_baseline.forward_pe)
    fwd_pe_premium = div(fpe.value, sp500_fwd_pe)
    fwd_pe_premium = None if fwd_pe_premium is None else fwd_pe_premium - 1

    return Valuation(
        pe=pe, forward_pe=fpe, ev_ebitda=eve, ev_revenue=evr, p_fcf=pfcf,
        vs_peers=vs_peers,
        vs_sp500=VsSP500(forward_pe_premium=derived_value(
            fwd_pe_premium, "fraction", ["valuation.forward_pe", "sp500_baseline.forward_pe"],
            type_=fpe.type)),
    )


def compute_metrics(factsheet: dict) -> dict:
    """factsheet.json -> metrics.json. Pure function."""
    fs = Factsheet.model_validate(factsheet)
    annual = fs.latest_annual_period
    balance = fs.latest_balance_period

    fcf_vo = free_cash_flow(fs, annual) if annual else derived_value(None, "usd", [])
    cash_flow = CashFlow(
        fcf=fcf_vo,
        fcf_conversion=fcf_conversion(fs, annual) if annual else derived_value(None, "fraction", []),
        fcf_yield=fcf_yield(fs, annual) if annual else derived_value(None, "fraction", []),
        capex_intensity=capex_intensity(fs, annual) if annual else derived_value(None, "fraction", []),
        ebitda=ebitda(fs, annual) if annual else derived_value(None, "usd", []),
    )

    prior = comparable_prior(fs, annual) if annual else None
    per_share = PerShare(
        dilution_yoy=dilution_yoy(fs, annual, prior) if prior else derived_value(None, "fraction", []),
        sbc_pct_revenue=sbc_pct_revenue(fs, annual) if annual else derived_value(None, "fraction", []),
        sbc_pct_fcf=sbc_pct_fcf(fs, annual) if annual else derived_value(None, "fraction", []),
    )

    metrics = Metrics(
        schema_version=fs.schema_version,
        ticker=fs.ticker,
        as_of=fs.as_of,
        latest_annual_period=annual,
        latest_balance_period=balance,
        margins=all_margins(fs),
        growth=all_growth(fs),
        cash_flow=cash_flow,
        balance_sheet=balance_sheet_metrics(fs),
        per_share=per_share,
        quality_flags=quality_flags(fs),
        valuation=_build_valuation(fs, cash_flow.ebitda.value, cash_flow.fcf.value),
        reverse_dcf=_reverse_dcf(fs, cash_flow.fcf.value),
    )
    return metrics.model_dump(mode="json")


def reverse_dcf(factsheet: dict, metrics: dict, assumptions: dict | None = None) -> dict:
    """Solve for the FCF growth the current price implies. Returns metrics.reverse_dcf
    (implied_fcf_cagr, assumptions tagged 'assumption', sensitivity_grid)."""
    fs = Factsheet.model_validate(factsheet)
    m = Metrics.model_validate(metrics)
    return _reverse_dcf(fs, m.cash_flow.fcf.value, assumptions).model_dump(mode="json")


def calculate_valuation(request: dict) -> dict:
    """The MCP-exposed valuation entry point (CalculateValuationRequest/Response).

    mcp_server/tools/calculate_valuation.py is a thin wrapper over this function
    and holds no formulas of its own. That wrapper is the ONE sanctioned
    cross-partition import in the repo (docs/adr/0007).

    In mock mode this loads the ACME factsheet by ticker; live mode wiring to a
    real factsheet lookup is P1's data.api.build_factsheet, invoked by the MCP
    tool wrapper (not by calc/, which stays free of I/O).
    """
    import json
    from pathlib import Path

    ticker = request["ticker"]
    mock_dir = Path(__file__).resolve().parents[1] / "fixtures" / "mock"
    fs_dict = json.loads((mock_dir / "factsheet.json").read_text(encoding="utf-8"))
    if fs_dict.get("ticker") != ticker:
        return {
            "metrics": None,
            "reverse_dcf": None,
            "notes": [f"No factsheet available for {ticker!r} in this mode."],
            "as_of": None,
            "truncated": False,
        }

    metrics = compute_metrics(fs_dict)
    assumptions = request.get("assumptions")
    rdcf = reverse_dcf(fs_dict, metrics, assumptions) if assumptions else metrics["reverse_dcf"]
    return {
        "metrics": metrics,
        "reverse_dcf": rdcf,
        "notes": [],
        "as_of": metrics["as_of"],
        "truncated": False,
    }


def evaluate_scenarios(
    scenarios: dict, factsheet: dict, metrics: dict, prior_shifts: list[dict] | None = None
) -> dict:
    """Scenarios -> ScenarioResult. Where every probability in the product is decided.

    Rejects requested weights that do not sum to 1.0; clamps each into a band
    around the defaults and records every clamp; computes price targets and
    annualized returns; starts P(beat S&P) from the base-rate prior and applies
    the SUM of `prior_shifts` (Scenario Agent plus Red Team) only within the
    hard cap (error C).

    Takes no `as_of`: the factsheet carries it.
    """
    scen = Scenarios.model_validate(scenarios)
    fs = Factsheet.model_validate(factsheet)
    m = Metrics.model_validate(metrics)
    shifts = (
        [PriorShift.model_validate(s) for s in prior_shifts]
        if prior_shifts is not None
        else [scen.prior_shift]
    )
    result = _evaluate_scenarios(scen, fs, m, shifts)
    return result.model_dump(mode="json")


def derive_scores(scenario_result: dict) -> dict:
    """ScenarioResult -> {short_term, medium_term, long_term} ints 1..10.

    A fixed rubric mapping excess return to a score. Documented in
    docs/p2/rubric.md. Never inflated, and never produced by an LLM.
    """
    sr = ScenarioResult.model_validate(scenario_result)
    return _derive_scores(sr).model_dump(mode="json")


def validate_consistency(scenario_result: dict, verdict_card: dict) -> dict:
    """Return {"ok": bool, "issues": [str]}.

    Score, P(beat S&P), expected return and the verdict enum must agree. A
    "strong_buy" whose expected return trails the index is an error, not a
    matter of taste.
    """
    sr = ScenarioResult.model_validate(scenario_result)
    card = VerdictCard.model_validate(verdict_card)
    return _validate_consistency(sr, card).model_dump(mode="json")
