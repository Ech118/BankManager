"""factsheet.json -> metrics.json. Pure functions, no I/O, no LLM (plan.txt
15.14 P2 step 1). P1 never computes margins/FCF/ratios; this is the only place
that does.
"""
from __future__ import annotations

from typing import Optional

from calc import config
from calc.dcf import compute_reverse_dcf
from calc.value import add, div, median, ratio_minus_one, read, sub, value, vo_value

DAYS_PER_YEAR = 365.0


def _prior_period_label(label: str) -> Optional[str]:
    """Same-period prior year: FY2025 -> FY2024, Q2-2026 -> Q2-2025."""
    if label.startswith("FY"):
        try:
            year = int(label[2:])
        except ValueError:
            return None
        return f"FY{year - 1}"
    if "-" in label:
        q, year = label.split("-", 1)
        try:
            year = int(year)
        except ValueError:
            return None
        return f"{q}-{year - 1}"
    return None


def _fcf(period: dict) -> Optional[float]:
    return sub(read(period, "op_cash_flow"), read(period, "capex"))


def _margins_for_period(label: str, period: dict) -> dict:
    revenue = read(period, "revenue")
    d = lambda *fields: [f"financials.{label}.{f}" for f in fields]  # noqa: E731
    return {
        "gross": value(div(read(period, "gross_profit"), revenue), "fraction", "fact",
                        derived_from=d("gross_profit", "revenue")),
        "operating": value(div(read(period, "operating_income"), revenue), "fraction", "fact",
                            derived_from=d("operating_income", "revenue")),
        "net": value(div(read(period, "net_income"), revenue), "fraction", "fact",
                      derived_from=d("net_income", "revenue")),
        "fcf": value(div(_fcf(period), revenue), "fraction", "fact",
                     derived_from=d("op_cash_flow", "capex", "revenue")),
    }


def _growth_for_period(label: str, cur: dict, prev: dict) -> dict:
    d = lambda cur_fields, prev_fields: (  # noqa: E731
        [f"financials.{label}.{f}" for f in cur_fields]
        + [f"financials.{_prior_period_label(label)}.{f}" for f in prev_fields]
    )
    return {
        "revenue_yoy": value(
            ratio_minus_one(read(cur, "revenue"), read(prev, "revenue")), "fraction", "fact",
            derived_from=d(["revenue"], ["revenue"])),
        "eps_yoy": value(
            ratio_minus_one(read(cur, "eps_diluted"), read(prev, "eps_diluted")), "fraction", "fact",
            derived_from=d(["eps_diluted"], ["eps_diluted"])),
        "fcf_yoy": value(
            ratio_minus_one(_fcf(cur), _fcf(prev)), "fraction", "fact",
            derived_from=d(["op_cash_flow", "capex"], ["op_cash_flow", "capex"])),
    }


def _dso_days(period: dict) -> Optional[float]:
    revenue = read(period, "revenue")
    if not revenue:
        return None
    recv = read(period, "receivables")
    if recv is None:
        return None
    return recv / revenue * DAYS_PER_YEAR


def _inventory_days(period: dict) -> Optional[float]:
    cost = read(period, "cost_of_revenue")
    if not cost:
        return None
    inv = read(period, "inventory")
    if inv is None:
        return None
    return inv / cost * DAYS_PER_YEAR


def _severity(pct_change: float, low: float, medium: float, high: float) -> Optional[str]:
    magnitude = abs(pct_change)
    if magnitude < low:
        return None
    if magnitude < medium:
        return "low"
    if magnitude < high:
        return "medium"
    return "high"


def _quality_flags(latest_annual_label: str, fin_annual: dict, prior_annual: Optional[dict],
                    per_share: dict, eps_yoy: Optional[float]) -> list[dict]:
    flags = []
    if prior_annual is not None:
        dso_now = _dso_days(fin_annual)
        dso_prev = _dso_days(prior_annual)
        if dso_now is not None and dso_prev is not None and dso_prev > 0:
            pct = dso_now / dso_prev - 1
            sev = _severity(pct, config.DSO_FLAG_LOW_PCT, config.DSO_FLAG_MEDIUM_PCT, config.DSO_FLAG_HIGH_PCT)
            if sev and pct > 0:
                flags.append({
                    "flag": "dso_rising",
                    "detail": (f"Days sales outstanding rose from {dso_prev:.1f} to {dso_now:.1f} days "
                               f"({_prior_period_label(latest_annual_label)} to {latest_annual_label}): "
                               "receivables grew faster than revenue."),
                    "severity": sev,
                })

        inv_now = _inventory_days(fin_annual)
        inv_prev = _inventory_days(prior_annual)
        if inv_now is not None and inv_prev is not None and inv_prev > 0:
            pct = inv_now / inv_prev - 1
            sev = _severity(pct, config.INVENTORY_DAYS_FLAG_LOW_PCT, config.INVENTORY_DAYS_FLAG_MEDIUM_PCT,
                             config.INVENTORY_DAYS_FLAG_HIGH_PCT)
            if sev and pct > 0:
                flags.append({
                    "flag": "inventory_days_rising",
                    "detail": (f"Days inventory outstanding rose from {inv_prev:.1f} to {inv_now:.1f} days "
                               f"({_prior_period_label(latest_annual_label)} to {latest_annual_label})."),
                    "severity": sev,
                })

    dilution = vo_value(per_share.get("dilution_yoy"))
    eps_growth = eps_yoy
    if dilution is not None and dilution < 0 and eps_growth is not None and eps_growth > 0:
        pct = abs(dilution)
        sev = _severity(pct, config.BUYBACK_FLAG_LOW_PCT, config.BUYBACK_FLAG_MEDIUM_PCT,
                         config.BUYBACK_FLAG_HIGH_PCT)
        if sev:
            flags.append({
                "flag": "buyback_flatters_eps",
                "detail": (f"Diluted share count fell {pct * 100:.1f}%, adding roughly {pct * 100:.1f} points "
                           f"to the {eps_growth * 100:.1f}% EPS growth."),
                "severity": sev,
            })
    return flags


def compute_metrics(factsheet: dict) -> dict:
    """factsheet.json -> metrics.json (schema/metrics.json)."""
    fin = factsheet["financials"]  # newest first, per contract
    by_label = {p["period"]: p for p in fin}

    annuals = [p for p in fin if p["form"] == "10-K"]
    latest_annual = annuals[0] if annuals else fin[0]
    latest_balance = fin[0]
    latest_annual_label = latest_annual["period"]
    latest_balance_label = latest_balance["period"]
    prior_annual_label = _prior_period_label(latest_annual_label)
    prior_annual = by_label.get(prior_annual_label)

    margins = {p["period"]: _margins_for_period(p["period"], p) for p in fin}

    growth = {}
    for p in fin:
        label = p["period"]
        prior_label = _prior_period_label(label)
        prior = by_label.get(prior_label)
        if prior is not None:
            growth[label] = _growth_for_period(label, p, prior)

    fcf = _fcf(latest_annual)
    ebitda = add(read(latest_annual, "operating_income"), read(latest_annual, "depreciation_amortization"))
    net_income = read(latest_annual, "net_income")
    revenue = read(latest_annual, "revenue")
    market_cap = vo_value(factsheet.get("market", {}).get("market_cap"))
    enterprise_value = vo_value(factsheet.get("market", {}).get("enterprise_value"))
    price = vo_value(factsheet.get("market", {}).get("price"))

    cash_flow = {
        "fcf": value(fcf, "usd", "fact",
                     derived_from=[f"financials.{latest_annual_label}.op_cash_flow",
                                   f"financials.{latest_annual_label}.capex"]),
        "fcf_conversion": value(div(fcf, net_income), "fraction", "fact",
                                 derived_from=["cash_flow.fcf", f"financials.{latest_annual_label}.net_income"]),
        "fcf_yield": value(div(fcf, market_cap), "fraction", "fact",
                            derived_from=["cash_flow.fcf", "market.market_cap"]),
        "capex_intensity": value(div(read(latest_annual, "capex"), revenue), "fraction", "fact",
                                  derived_from=[f"financials.{latest_annual_label}.capex",
                                                f"financials.{latest_annual_label}.revenue"]),
        "ebitda": value(ebitda, "usd", "fact",
                         derived_from=[f"financials.{latest_annual_label}.operating_income",
                                       f"financials.{latest_annual_label}.depreciation_amortization"]),
    }

    net_debt = sub(read(latest_balance, "total_debt"), read(latest_balance, "cash"))
    balance_sheet = {
        "net_debt": value(net_debt, "usd", "fact",
                           derived_from=[f"financials.{latest_balance_label}.total_debt",
                                         f"financials.{latest_balance_label}.cash"]),
        "net_debt_to_ebitda": value(div(net_debt, ebitda), "multiple", "fact",
                                     derived_from=["balance_sheet.net_debt", "cash_flow.ebitda"]),
        "interest_coverage": value(
            div(read(latest_annual, "operating_income"), read(latest_annual, "interest_expense")),
            "multiple", "fact",
            derived_from=[f"financials.{latest_annual_label}.operating_income",
                          f"financials.{latest_annual_label}.interest_expense"]),
        "current_ratio": value(
            div(read(latest_balance, "current_assets"), read(latest_balance, "current_liabilities")),
            "ratio", "fact",
            derived_from=[f"financials.{latest_balance_label}.current_assets",
                          f"financials.{latest_balance_label}.current_liabilities"]),
    }

    dilution_yoy = None
    sbc_pct_revenue = None
    sbc_pct_fcf = None
    if prior_annual is not None:
        dilution_yoy = ratio_minus_one(read(latest_annual, "shares_diluted"), read(prior_annual, "shares_diluted"))
    sbc = read(latest_annual, "sbc")
    sbc_pct_revenue = div(sbc, revenue)
    sbc_pct_fcf = div(sbc, fcf)
    per_share = {
        "dilution_yoy": value(dilution_yoy, "fraction", "fact",
                               derived_from=[f"financials.{latest_annual_label}.shares_diluted",
                                             f"financials.{prior_annual_label}.shares_diluted"]) if prior_annual
                        else value(None, "fraction", "fact"),
        "sbc_pct_revenue": value(sbc_pct_revenue, "fraction", "fact",
                                  derived_from=[f"financials.{latest_annual_label}.sbc",
                                                f"financials.{latest_annual_label}.revenue"]),
        "sbc_pct_fcf": value(sbc_pct_fcf, "fraction", "fact",
                              derived_from=[f"financials.{latest_annual_label}.sbc", "cash_flow.fcf"]),
    }

    eps_yoy_vo = growth.get(latest_annual_label, {}).get("eps_yoy")
    quality_flags = _quality_flags(latest_annual_label, latest_annual, prior_annual, per_share,
                                    vo_value(eps_yoy_vo))

    eps = read(latest_annual, "eps_diluted")
    pe = div(price, eps)
    consensus = factsheet.get("consensus") or {}
    eps_next_fy = vo_value(consensus.get("eps_next_fy"))
    forward_pe = div(price, eps_next_fy)
    ev_ebitda = div(enterprise_value, ebitda)
    ev_revenue = div(enterprise_value, revenue)
    p_fcf = div(market_cap, fcf)

    peers = factsheet.get("peers") or []
    peer_pe_median = median([vo_value(pr.get("pe")) for pr in peers])
    peer_ev_ebitda_median = median([vo_value(pr.get("ev_ebitda")) for pr in peers])
    sp500_forward_pe = vo_value(factsheet.get("sp500_baseline", {}).get("forward_pe"))

    valuation = {
        "pe": value(pe, "multiple", "fact",
                    derived_from=["market.price", f"financials.{latest_annual_label}.eps_diluted"]),
        "forward_pe": value(forward_pe, "multiple", "estimate",
                             derived_from=["market.price", "consensus.eps_next_fy"]),
        "ev_ebitda": value(ev_ebitda, "multiple", "fact",
                            derived_from=["market.enterprise_value", "cash_flow.ebitda"]),
        "ev_revenue": value(ev_revenue, "multiple", "fact",
                             derived_from=["market.enterprise_value", f"financials.{latest_annual_label}.revenue"]),
        "p_fcf": value(p_fcf, "multiple", "fact",
                        derived_from=["market.market_cap", "cash_flow.fcf"]),
        "vs_peers": {
            "pe_premium": value(ratio_minus_one(pe, peer_pe_median), "fraction", "fact",
                                 derived_from=["valuation.pe", "peers[*].pe"]),
            "ev_ebitda_premium": value(ratio_minus_one(ev_ebitda, peer_ev_ebitda_median), "fraction", "fact",
                                        derived_from=["valuation.ev_ebitda", "peers[*].ev_ebitda"]),
        },
        "vs_sp500": {
            "forward_pe_premium": value(ratio_minus_one(forward_pe, sp500_forward_pe), "fraction", "estimate",
                                         derived_from=["valuation.forward_pe", "sp500_baseline.forward_pe"]),
        },
    }

    reverse_dcf = compute_reverse_dcf(enterprise_value, fcf)

    return {
        "schema_version": factsheet["schema_version"],
        "ticker": factsheet["ticker"],
        "as_of": factsheet["as_of"],
        "latest_annual_period": latest_annual_label,
        "latest_balance_period": latest_balance_label,
        "margins": margins,
        "growth": growth,
        "cash_flow": cash_flow,
        "balance_sheet": balance_sheet,
        "per_share": per_share,
        "quality_flags": quality_flags,
        "valuation": valuation,
        "reverse_dcf": reverse_dcf,
    }
