"""Trading multiples. Specified by docs/data-model.md "Metrics.valuation".

Every multiple here is a ratio of a market number to a reported one, so each has
the same two failure modes: the market number is missing (rare), or the reported
denominator does not exist for this filer (common). Both yield `unavailable` with
a reason, never 0 and never a silently dropped key.

Enterprise value is `market_cap + total_debt - cash` (CLAUDE.md sign
conventions). P1 already publishes it on the market snapshot; calc/ recomputes it
from its parts when it is absent, so the definition lives in exactly one place.

For a bank, insurer, broker or REIT the EV-based multiples are `not_applicable`
and **P/B is the one that means something**, so it is computed for every filer
and flagged as the primary multiple for financials (P1 -> P2, 2026-09-19).
"""

from __future__ import annotations

from calc import config
from calc.facts import Ledger, missing_reason, nums, present
from calc.metrics.ttm import TTM_PERIOD_LABEL, derived_ttm, flow_ref
from calc.value import div, median, ratio_minus_one, sub

EV_BANK_REASON = (
    "not applicable to a bank, insurer, broker or REIT: enterprise value treats "
    "debt as funding for operations, but for this filer debt IS the operation"
)
NO_PEER_MULTIPLES = (
    "the factsheet's peers carry a market cap but no multiples, so there is no "
    "peer median to compare against (P1 records current quotes only)"
)


def enterprise_value(ledger: Ledger, balance_period: str) -> dict:
    """market_cap + total_debt - cash, or P1's own figure when it published one."""
    published = ledger.market_ref("enterprise_value")
    if published is not None:
        return {"ref": published, "vo": None}
    inputs = {
        "market_cap": ledger.market_ref("market_cap"),
        "total_debt": ledger.ref(balance_period, "total_debt"),
        "cash": ledger.ref(balance_period, "cash"),
    }
    values = nums(inputs)
    total = None
    if None not in values.values():
        total = values["market_cap"] + values["total_debt"] - values["cash"]
    vo = ledger.emit(
        total,
        metric="enterprise_value",
        period=balance_period,
        unit="usd",
        formula="market_cap + total_debt - cash",
        inputs=present(inputs),
        paths=[
            "market.market_cap",
            f"financials.{balance_period}.total_debt",
            f"financials.{balance_period}.cash",
        ],
        period_type="instant",
        reason=missing_reason(inputs, balance_period),
    )
    return {"ref": ledger.derived_ref(vo, "enterprise_value"), "vo": vo}


def multiples(
    ledger: Ledger,
    *,
    annual: str,
    balance: str,
    ebitda: dict,
    fcf: dict,
    partial_scope: bool = False,
) -> dict:
    """P/E, forward P/E, EV/EBITDA, EV/Revenue, P/FCF, P/B and the peer comparison."""
    price = ledger.market_ref("price")
    market_cap = ledger.market_ref("market_cap")
    ev = enterprise_value(ledger, balance)["ref"]

    out: dict = {}

    basis: dict[str, str] = {}

    eps_ref, eps_basis = flow_ref(ledger, annual, "eps_diluted")
    basis["pe"] = eps_basis
    inputs = {"price": price, "eps_diluted": eps_ref}
    values = nums(inputs)
    out["pe"] = ledger.emit(
        div(values["price"], values["eps_diluted"]),
        metric="pe",
        period=_label(annual, eps_basis),
        unit="multiple",
        formula="price / eps_diluted",
        inputs=present(inputs),
        paths=["market.price", _path(annual, eps_basis, "eps_diluted")],
        period_type="instant",
        reason=missing_reason(inputs, annual),
    )
    out["pe"]["basis"] = eps_basis

    inputs = {
        "price": price,
        "consensus_eps_next_fy": ledger.top_level_ref("consensus", "eps_next_fy"),
    }
    values = nums(inputs)
    out["forward_pe"] = ledger.emit(
        div(values["price"], values["consensus_eps_next_fy"]),
        metric="forward_pe",
        period=annual,
        unit="multiple",
        formula="price / consensus_eps_next_fy",
        inputs=present(inputs),
        paths=["market.price", "consensus.eps_next_fy"],
        period_type="instant",
        value_type="estimate",
        reason=(
            "no next-year consensus EPS on the factsheet, so a forward multiple would "
            "be our own forecast dressed as the market's"
            if inputs["consensus_eps_next_fy"] is None
            else missing_reason(inputs, annual)
        ),
    )

    ebitda_ttm = (
        None
        if partial_scope
        else derived_ttm(
            ledger,
            "ebitda_ttm",
            {
                "operating_income": "operating_income",
                "depreciation_amortization": "depreciation_amortization",
            },
            annual,
        )
    )
    ebitda_used = ebitda_ttm or ebitda
    basis["ev_ebitda"] = "ttm" if ebitda_ttm else "latest_full_year"
    inputs = {"enterprise_value": ev, "ebitda": ledger.derived_ref(ebitda_used, "ebitda")}
    values = nums(inputs)
    out["ev_ebitda"] = ledger.emit(
        None if partial_scope else div(values["enterprise_value"], values["ebitda"]),
        metric="ev_ebitda",
        period=_label(annual, basis["ev_ebitda"]),
        unit="multiple",
        formula="enterprise_value / ebitda",
        inputs=present(inputs),
        paths=[
            "market.enterprise_value",
            "ttm.ebitda" if ebitda_ttm else "cash_flow.ebitda",
        ],
        period_type="instant",
        reason=EV_BANK_REASON if partial_scope else missing_reason(inputs, annual),
        not_applicable=partial_scope,
    )
    out["ev_ebitda"]["basis"] = basis["ev_ebitda"]

    revenue_ref, revenue_basis = flow_ref(ledger, annual, "revenue")
    basis["ev_revenue"] = basis["p_s"] = revenue_basis
    inputs = {"enterprise_value": ev, "revenue": revenue_ref}
    values = nums(inputs)
    out["ev_revenue"] = ledger.emit(
        None if partial_scope else div(values["enterprise_value"], values["revenue"]),
        metric="ev_revenue",
        period=_label(annual, revenue_basis),
        unit="multiple",
        formula="enterprise_value / revenue",
        inputs=present(inputs),
        paths=["market.enterprise_value", _path(annual, revenue_basis, "revenue")],
        period_type="instant",
        reason=EV_BANK_REASON if partial_scope else missing_reason(inputs, annual),
        not_applicable=partial_scope,
    )
    out["ev_revenue"]["basis"] = revenue_basis

    fcf_ttm = (
        None
        if partial_scope
        else derived_ttm(
            ledger, "fcf_ttm", {"op_cash_flow": "op_cash_flow", "capex": "capex"}, annual
        )
    )
    fcf_used = fcf_ttm or fcf
    basis["p_fcf"] = "ttm" if fcf_ttm else "latest_full_year"
    inputs = {"market_cap": market_cap, "fcf": ledger.derived_ref(fcf_used, "fcf")}
    values = nums(inputs)
    out["p_fcf"] = ledger.emit(
        div(values["market_cap"], values["fcf"]),
        metric="p_fcf",
        period=_label(annual, basis["p_fcf"]),
        unit="multiple",
        formula="market_cap / fcf",
        inputs=present(inputs),
        paths=["market.market_cap", "ttm.fcf" if fcf_ttm else "cash_flow.fcf"],
        period_type="instant",
        reason=(
            fcf.get("unavailable_reason")
            if fcf.get("not_applicable")
            else missing_reason(inputs, annual)
        ),
        not_applicable=bool(fcf.get("not_applicable")),
    )

    out["p_fcf"]["basis"] = basis["p_fcf"]

    inputs = {"market_cap": market_cap, "revenue": revenue_ref}
    values = nums(inputs)
    out["p_s"] = ledger.emit(
        div(values["market_cap"], values["revenue"]),
        metric="p_s",
        period=_label(annual, revenue_basis),
        unit="multiple",
        formula="market_cap / revenue",
        inputs=present(inputs),
        paths=["market.market_cap", _path(annual, revenue_basis, "revenue")],
        period_type="instant",
        reason=missing_reason(inputs, annual),
    )
    out["p_s"]["basis"] = revenue_basis

    inputs = {"market_cap": market_cap, "total_equity": ledger.ref(balance, "total_equity")}
    values = nums(inputs)
    out["p_b"] = ledger.emit(
        div(values["market_cap"], values["total_equity"]),
        metric="p_b",
        period=balance,
        unit="multiple",
        formula="market_cap / total_equity",
        inputs=present(inputs),
        paths=["market.market_cap", f"financials.{balance}.total_equity"],
        period_type="instant",
        reason=missing_reason(inputs, balance),
    )
    out["primary_multiple"] = "p_b" if partial_scope else "pe"
    basis["p_b"] = "latest_balance_sheet"
    out["p_b"]["basis"] = basis["p_b"]
    trailing = sorted(name for name, how in basis.items() if how == "ttm")
    full_year = sorted(name for name, how in basis.items() if how == "latest_full_year")
    out["basis"] = {
        "earnings_basis": "ttm" if trailing else "latest_full_year",
        "by_multiple": dict(basis),
        "ttm_multiples": trailing,
        "full_year_multiples": full_year,
        "earnings_period": TTM_PERIOD_LABEL if trailing else annual,
        "latest_annual_period": annual,
        "balance_period": balance,
        "note": (
            f"{', '.join(trailing)} divide a TRAILING TWELVE MONTH figure, the basis a data "
            f"provider quotes. {', '.join(full_year) or 'Nothing else'} divides the latest "
            f"full year ({annual}). `by_multiple` labels each one."
            if trailing
            else (
                f"every multiple divides today's price by {annual}, the latest FULL YEAR "
                "(CLAUDE.md: flow metrics use the latest full year). A data provider quotes a "
                "TRAILING TWELVE MONTH multiple, so when a fiscal year is partly elapsed and "
                "earnings are growing, the figure here is HIGHER than the one a reader sees on "
                "a finance site - AAPL is 45x on FY2025 EPS of $7.46 against about 36x on TTM "
                "EPS. calc/ uses a TTM figure the moment the factsheet carries a "
                "`<metric>_ttm` fact; this one does not (asked of P1)."
            )
        ),
    }

    out["vs_peers"] = vs_peers(ledger, out)
    out["vs_sp500"] = vs_sp500(ledger, out)
    return out


def peer_median(ledger: Ledger, field: str) -> tuple[float | None, list[str]]:
    """Median of one multiple across the factsheet's peers, and who contributed."""
    contributors: list[str] = []
    values: list[float | None] = []
    for peer in ledger.factsheet.get("peers") or []:
        vo = peer.get(field)
        if isinstance(vo, dict) and vo.get("status") == "ok" and vo.get("value") is not None:
            values.append(float(vo["value"]))
            contributors.append(peer.get("ticker") or "?")
    if len(values) < config.PEER_MIN_SAMPLE:
        return None, contributors
    return median(values), contributors


def vs_peers(ledger: Ledger, valuation: dict) -> dict:
    """Premium (+) or discount (-) to the peer median, as fractions."""
    out: dict = {}
    for key, field in (("pe_premium", "pe"), ("ev_ebitda_premium", "ev_ebitda")):
        med, contributors = peer_median(ledger, field)
        own = valuation[field].get("value")
        reason = NO_PEER_MULTIPLES if med is None else None
        if reason is None and own is None:
            reason = f"this company's {field} is unavailable, so a premium cannot be computed"
        own_ref = ledger.derived_ref(valuation[field], field)
        if reason is None and own_ref is None:
            reason = f"this company's {field} carries no derived fact to compare"
        # The peer median goes into the formula as a LITERAL: individual peer
        # multiples have no fact ids, so a variable would make the derivation
        # unrecomputable. The contributing tickers are recorded alongside it.
        out[key] = ledger.emit(
            ratio_minus_one(own, med) if reason is None else None,
            metric=f"{field}_premium_vs_peers",
            period=ledger.latest_annual_label() or ledger.as_of,
            unit="fraction",
            formula=f"{field} / {med!r} - 1",
            inputs=present({field: own_ref}),
            paths=[f"valuation.{field}", f"peers[*].{field}"],
            period_type="instant",
            reason=reason,
            derivation_extra={"peer_tickers": contributors, "peer_median": med},
        )
    return out


def vs_sp500(ledger: Ledger, valuation: dict) -> dict:
    """Premium or discount to the index's forward multiple."""
    baseline = ledger.top_level_ref("sp500_baseline", "forward_pe")
    own_ref = ledger.derived_ref(valuation["forward_pe"], "forward_pe")
    own = valuation["forward_pe"].get("value")
    index = None if baseline is None else baseline.value
    reason = None
    if own is None or own_ref is None:
        reason = valuation["forward_pe"].get("unavailable_reason") or "forward P/E unavailable"
    elif index is None:
        reason = "no S&P 500 forward P/E on the factsheet"
    return {
        "forward_pe_premium": ledger.emit(
            ratio_minus_one(own, index) if reason is None else None,
            metric="forward_pe_premium_vs_sp500",
            period=ledger.latest_annual_label() or ledger.as_of,
            unit="fraction",
            formula="forward_pe / sp500_baseline_forward_pe - 1",
            inputs=present({"forward_pe": own_ref, "sp500_baseline_forward_pe": baseline}),
            paths=["valuation.forward_pe", "sp500_baseline.forward_pe"],
            period_type="instant",
            value_type="estimate",
            reason=reason,
        )
    }


def net_debt(ledger: Ledger, balance: str) -> float | None:
    """Positive when debt exceeds cash. Used by the DCF bridge."""
    return sub(
        _num(ledger.ref(balance, "total_debt")),
        _num(ledger.ref(balance, "cash")),
    )


def _num(ref) -> float | None:
    return None if ref is None else ref.value


def _label(annual: str, basis: str) -> str:
    """The fiscal_period a derived multiple is filed under.

    Always a real fiscal period, even for a TTM multiple: `FinancialFact.fiscal_period`
    must match FY followed by four digits, or a quarter label, so "TTM" is not a
    legal value there. Which
    basis was used is on the ValueObject (`basis`) and visible in the derived fact's
    own `input_fact_ids`, which point at the `_ttm` facts.
    """
    return annual


def _path(annual: str, basis: str, field: str) -> str:
    """The dotted path a reader follows to the denominator."""
    return f"ttm.{field}" if basis == "ttm" else f"financials.{annual}.{field}"
