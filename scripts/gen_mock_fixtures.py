#!/usr/bin/env python3
"""Generate fixtures/mock/*.json for the FICTIONAL company ACME.

FROZEN (Step 0). Run with:  make gen-mock
All derived numbers are computed here from the base reported numbers, and the
hand-check asserts at the bottom pin the values a human verified. ACME is not a
real company; nothing here is market data. P2's calc/ is the authority for the
real formulas - these are simple stand-ins so the mock is internally consistent.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "fixtures" / "mock"
SEC = OUT / "sections"

SCHEMA_VERSION = "1.0.0"
TICKER = "ACME"
AS_OF = "2026-09-19"
BUILT_AT = "2026-09-19T12:00:00Z"
DISCLAIMER = (
    "This is AI-generated research for educational purposes only. It is not "
    "investment advice or a recommendation to buy or sell any security."
)


def v(value, unit, type_="fact", source_id=None, derived_from=None):
    """Build a VALUE OBJECT (schema/common.json#/$defs/value)."""
    out = {
        "value": None if value is None else round(value, 10),
        "unit": unit,
        "type": type_,
        "status": "unavailable" if value is None else "ok",
        "source_id": source_id,
    }
    if derived_from:
        out["derived_from"] = derived_from
    return out


# --------------------------------------------------------------------------
# Base reported numbers (USD, full dollars). Newest first.
# --------------------------------------------------------------------------
PERIODS = {
    "Q2-2026": dict(
        period_end="2026-06-30", form="10-Q", filed="2026-08-05", acc="0001234567-26-000090",
        revenue=1_400_000_000, cost=830_000_000, op=235_000_000, interest=14_000_000,
        tax_rate=0.20, shares=395_000_000, da=52_000_000, ocf=230_000_000, capex=70_000_000,
        sbc=27_000_000, cash=1_000_000_000, debt=1_150_000_000, assets=6_200_000_000,
        equity=3_150_000_000, ca=2_500_000_000, cl=1_350_000_000, recv=760_000_000,
        inv=520_000_000, eps=0.45),
    "FY2025": dict(
        period_end="2025-12-31", form="10-K", filed="2026-02-20", acc="0001234567-26-000010",
        revenue=5_000_000_000, cost=3_000_000_000, op=800_000_000, interest=60_000_000,
        tax_rate=0.20, shares=400_000_000, da=200_000_000, ocf=850_000_000, capex=250_000_000,
        sbc=100_000_000, cash=900_000_000, debt=1_200_000_000, assets=6_000_000_000,
        equity=3_000_000_000, ca=2_400_000_000, cl=1_300_000_000, recv=700_000_000,
        inv=500_000_000, eps=1.48),
    "FY2024": dict(
        period_end="2024-12-31", form="10-K", filed="2025-02-21", acc="0001234567-25-000010",
        revenue=4_500_000_000, cost=2_750_000_000, op=675_000_000, interest=65_000_000,
        tax_rate=0.20, shares=410_000_000, da=190_000_000, ocf=700_000_000, capex=220_000_000,
        sbc=90_000_000, cash=700_000_000, debt=1_300_000_000, assets=5_500_000_000,
        equity=2_700_000_000, ca=2_100_000_000, cl=1_200_000_000, recv=600_000_000,
        inv=450_000_000, eps=1.19),
    "FY2023": dict(
        period_end="2023-12-31", form="10-K", filed="2024-02-22", acc="0001234567-24-000010",
        revenue=4_100_000_000, cost=2_560_000_000, op=574_000_000, interest=70_000_000,
        tax_rate=0.20, shares=415_000_000, da=180_000_000, ocf=600_000_000, capex=200_000_000,
        sbc=80_000_000, cash=550_000_000, debt=1_400_000_000, assets=5_100_000_000,
        equity=2_400_000_000, ca=1_900_000_000, cl=1_100_000_000, recv=520_000_000,
        inv=420_000_000, eps=0.97),
}
for p in PERIODS.values():
    p["gp"] = p["revenue"] - p["cost"]
    p["pretax"] = p["op"] - p["interest"]
    p["ni"] = p["pretax"] * (1 - p["tax_rate"])
    p["fcf"] = p["ocf"] - p["capex"]

FY = PERIODS["FY2025"]
FY_PRIOR = PERIODS["FY2024"]
LATEST_BS = PERIODS["Q2-2026"]

PRICE = 50.0
SHARES_OUT = 395_000_000
MARKET_CAP = PRICE * SHARES_OUT
EV = MARKET_CAP + LATEST_BS["debt"] - LATEST_BS["cash"]
EPS_NEXT = 1.70
SP_FWD_PE = 22.0
RF = 0.043

# Source ids
S_QUOTE = "src:market:quote"
S_PEERS = "src:market:peers"
S_SP = "src:market:sp500"
S_FRED = "src:fred:DGS10"
S_CONS = "src:market:consensus"
S_NEWS1 = "src:news:1"
S_NEWS2 = "src:news:2"
ACC10K = FY["acc"]
S_BUS = f"src:edgar:{ACC10K}:business"
S_RISK = f"src:edgar:{ACC10K}:risk_factors"
S_MDNA = f"src:edgar:{ACC10K}:mdna"
S_CALC = "src:config:calc_assumptions"
S_LLM = "src:llm:valuation"


def xbrl(acc):
    return f"src:edgar:{acc}:xbrl"


# --------------------------------------------------------------------------
# factsheet.json
# --------------------------------------------------------------------------
def fin_entry(label, p):
    s = xbrl(p["acc"])
    return {
        "period": label,
        "period_end": p["period_end"],
        "form": p["form"],
        "filed_date": p["filed"],
        "accession": p["acc"],
        "revenue": v(p["revenue"], "usd", "fact", s),
        "cost_of_revenue": v(p["cost"], "usd", "fact", s),
        "gross_profit": v(p["gp"], "usd", "fact", s),
        "operating_income": v(p["op"], "usd", "fact", s),
        "pretax_income": v(p["pretax"], "usd", "fact", s),
        "net_income": v(p["ni"], "usd", "fact", s),
        "eps_diluted": v(p["eps"], "usd_per_share", "fact", s),
        "shares_diluted": v(p["shares"], "shares", "fact", s),
        "depreciation_amortization": v(p["da"], "usd", "fact", s),
        "op_cash_flow": v(p["ocf"], "usd", "fact", s),
        "capex": v(p["capex"], "usd", "fact", s),
        "sbc": v(p["sbc"], "usd", "fact", s),
        "cash": v(p["cash"], "usd", "fact", s),
        "total_debt": v(p["debt"], "usd", "fact", s),
        "interest_expense": v(p["interest"], "usd", "fact", s),
        "total_assets": v(p["assets"], "usd", "fact", s),
        "total_equity": v(p["equity"], "usd", "fact", s),
        "current_assets": v(p["ca"], "usd", "fact", s),
        "current_liabilities": v(p["cl"], "usd", "fact", s),
        "receivables": v(p["recv"], "usd", "fact", s),
        "inventory": v(p["inv"], "usd", "fact", s),
    }


PEERS_RAW = [
    ("PRAA", 12e9, 22.0, 14.0, 2.5, 0.045),
    ("PRBB", 30e9, 25.0, 15.0, 3.0, 0.040),
    ("PRCC", 18e9, 28.0, 16.0, 3.2, 0.038),
    ("PRDD", 25e9, 30.0, 18.0, 3.6, 0.033),
]


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def section_meta(name, fname):
    text = (SEC / fname).read_text()
    return {
        "name": name,
        "source_id": f"src:edgar:{ACC10K}:{name}",
        "accession": ACC10K,
        "form": "10-K",
        "period": "FY2025",
        "char_count": len(text),
    }


def build_factsheet():
    sources = {}
    for label, p in PERIODS.items():
        sources[xbrl(p["acc"])] = {
            "kind": "edgar_xbrl", "url": None, "accession": p["acc"], "fetched_at": BUILT_AT}
    for sid in (S_BUS, S_RISK, S_MDNA):
        sources[sid] = {"kind": "edgar_text", "url": None, "accession": ACC10K, "fetched_at": BUILT_AT}
    for sid, kind in ((S_QUOTE, "market"), (S_PEERS, "market"), (S_SP, "market"),
                      (S_CONS, "market"), (S_FRED, "fred"), (S_NEWS1, "news"), (S_NEWS2, "news")):
        sources[sid] = {"kind": kind, "url": None, "accession": None, "fetched_at": BUILT_AT}
    return {
        "schema_version": SCHEMA_VERSION,
        "ticker": TICKER,
        "company_name": "Acme Corporation (fictional mock)",
        "as_of": AS_OF,
        "built_at": BUILT_AT,
        "mode": "mock",
        "scope": {"in_scope": True, "reason": None},
        "data_quality": {"overall": "ok", "gaps": []},
        "market": {
            "price": v(PRICE, "usd_per_share", "fact", S_QUOTE),
            "market_cap": v(MARKET_CAP, "usd", "fact", S_QUOTE),
            "shares_outstanding": v(SHARES_OUT, "shares", "fact", S_QUOTE),
            "enterprise_value": v(
                EV, "usd", "fact", None,
                ["market.market_cap", "financials.Q2-2026.total_debt", "financials.Q2-2026.cash"]),
        },
        "financials": [fin_entry(k, p) for k, p in PERIODS.items()],
        "peers": [
            {
                "ticker": t,
                "market_cap": v(mc, "usd", "fact", S_PEERS),
                "pe": v(pe, "multiple", "fact", S_PEERS),
                "ev_ebitda": v(eve, "multiple", "fact", S_PEERS),
                "ev_revenue": v(evr, "multiple", "fact", S_PEERS),
                "fcf_yield": v(fy, "fraction", "fact", S_PEERS),
            }
            for t, mc, pe, eve, evr, fy in PEERS_RAW
        ],
        "sp500_baseline": {
            "forward_pe": v(SP_FWD_PE, "multiple", "estimate", S_SP),
            "earnings_yield": v(1 / SP_FWD_PE, "fraction", "estimate", S_SP,
                                ["sp500_baseline.forward_pe"]),
            "risk_free_rate": v(RF, "fraction", "fact", S_FRED),
            "as_of": "2026-09-18",
        },
        "consensus": {
            "revenue_next_fy": v(5_450_000_000, "usd", "estimate", S_CONS),
            "eps_next_fy": v(EPS_NEXT, "usd_per_share", "estimate", S_CONS),
        },
        "filing_sections": [
            section_meta("business", "business.txt"),
            section_meta("risk_factors", "risk_factors.txt"),
            section_meta("mdna", "mdna.txt"),
        ],
        "news": [
            {"headline": "Acme wins multi-year sensor contract with European automaker (mock)",
             "date": "2026-09-02", "url": "https://example.com/mock-news-1", "source_id": S_NEWS1},
            {"headline": "Rival bundles software free with hardware in mid-market push (mock)",
             "date": "2026-08-27", "url": "https://example.com/mock-news-2", "source_id": S_NEWS2},
        ],
        "sources": sources,
    }


# --------------------------------------------------------------------------
# metrics.json
# --------------------------------------------------------------------------
def fpath(period, field):
    return f"financials.{period}.{field}"


def reverse_dcf_solve(r, tg, ev=EV, fcf0=FY["fcf"], n=10):
    def pv(g):
        s, f = 0.0, fcf0
        for t in range(1, n + 1):
            f *= 1 + g
            s += f / (1 + r) ** t
        return s + f * (1 + tg) / (r - tg) / (1 + r) ** n

    lo, hi = -0.5, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if pv(mid) > ev else (mid, hi)
    return (lo + hi) / 2


def build_metrics():
    margins, growth = {}, {}
    for label, p in PERIODS.items():
        d = lambda f: [fpath(label, f)]  # noqa: E731
        margins[label] = {
            "gross": v(p["gp"] / p["revenue"], "fraction", "fact", None, d("gross_profit") + d("revenue")),
            "operating": v(p["op"] / p["revenue"], "fraction", "fact", None, d("operating_income") + d("revenue")),
            "net": v(p["ni"] / p["revenue"], "fraction", "fact", None, d("net_income") + d("revenue")),
            "fcf": v(p["fcf"] / p["revenue"], "fraction", "fact", None,
                     d("op_cash_flow") + d("capex") + d("revenue")),
        }
    for cur, prev in (("FY2025", "FY2024"), ("FY2024", "FY2023")):
        c, p = PERIODS[cur], PERIODS[prev]
        growth[cur] = {
            "revenue_yoy": v(c["revenue"] / p["revenue"] - 1, "fraction", "fact", None,
                             [fpath(cur, "revenue"), fpath(prev, "revenue")]),
            "eps_yoy": v(c["eps"] / p["eps"] - 1, "fraction", "fact", None,
                         [fpath(cur, "eps_diluted"), fpath(prev, "eps_diluted")]),
            "fcf_yoy": v(c["fcf"] / p["fcf"] - 1, "fraction", "fact", None,
                         [fpath(cur, "op_cash_flow"), fpath(cur, "capex"),
                          fpath(prev, "op_cash_flow"), fpath(prev, "capex")]),
        }

    ebitda = FY["op"] + FY["da"]
    net_debt = LATEST_BS["debt"] - LATEST_BS["cash"]
    pe = PRICE / FY["eps"]
    fwd_pe = PRICE / EPS_NEXT
    ev_ebitda = EV / ebitda
    peer_pe_med = median([x[2] for x in PEERS_RAW])
    peer_eve_med = median([x[3] for x in PEERS_RAW])
    dso_now = FY["recv"] / FY["revenue"] * 365
    dso_prev = FY_PRIOR["recv"] / FY_PRIOR["revenue"] * 365

    grid = []
    for r in (0.08, 0.09, 0.10):
        for tg in (0.02, 0.03, 0.04):
            grid.append({
                "discount_rate": r, "terminal_growth": tg,
                "implied_fcf_cagr": v(reverse_dcf_solve(r, tg), "fraction", "fact", None,
                                      ["market.enterprise_value", "cash_flow.fcf"]),
            })
    base_cagr = reverse_dcf_solve(0.09, 0.03)

    return {
        "schema_version": SCHEMA_VERSION,
        "ticker": TICKER,
        "as_of": AS_OF,
        "latest_annual_period": "FY2025",
        "latest_balance_period": "Q2-2026",
        "margins": margins,
        "growth": growth,
        "cash_flow": {
            "fcf": v(FY["fcf"], "usd", "fact", None, [fpath("FY2025", "op_cash_flow"), fpath("FY2025", "capex")]),
            "fcf_conversion": v(FY["fcf"] / FY["ni"], "fraction", "fact", None,
                                ["cash_flow.fcf", fpath("FY2025", "net_income")]),
            "fcf_yield": v(FY["fcf"] / MARKET_CAP, "fraction", "fact", None,
                           ["cash_flow.fcf", "market.market_cap"]),
            "capex_intensity": v(FY["capex"] / FY["revenue"], "fraction", "fact", None,
                                 [fpath("FY2025", "capex"), fpath("FY2025", "revenue")]),
            "ebitda": v(ebitda, "usd", "fact", None,
                        [fpath("FY2025", "operating_income"), fpath("FY2025", "depreciation_amortization")]),
        },
        "balance_sheet": {
            "net_debt": v(net_debt, "usd", "fact", None,
                          [fpath("Q2-2026", "total_debt"), fpath("Q2-2026", "cash")]),
            "net_debt_to_ebitda": v(net_debt / ebitda, "multiple", "fact", None,
                                    ["balance_sheet.net_debt", "cash_flow.ebitda"]),
            "interest_coverage": v(FY["op"] / FY["interest"], "multiple", "fact", None,
                                   [fpath("FY2025", "operating_income"), fpath("FY2025", "interest_expense")]),
            "current_ratio": v(LATEST_BS["ca"] / LATEST_BS["cl"], "ratio", "fact", None,
                               [fpath("Q2-2026", "current_assets"), fpath("Q2-2026", "current_liabilities")]),
        },
        "per_share": {
            "dilution_yoy": v(FY["shares"] / FY_PRIOR["shares"] - 1, "fraction", "fact", None,
                              [fpath("FY2025", "shares_diluted"), fpath("FY2024", "shares_diluted")]),
            "sbc_pct_revenue": v(FY["sbc"] / FY["revenue"], "fraction", "fact", None,
                                 [fpath("FY2025", "sbc"), fpath("FY2025", "revenue")]),
            "sbc_pct_fcf": v(FY["sbc"] / FY["fcf"], "fraction", "fact", None,
                             [fpath("FY2025", "sbc"), "cash_flow.fcf"]),
        },
        "quality_flags": [
            {
                "flag": "dso_rising",
                "detail": f"Days sales outstanding rose from {dso_prev:.1f} to {dso_now:.1f} days "
                          "(FY2024 to FY2025): receivables grew faster than revenue.",
                "severity": "low",
            },
            {
                "flag": "buyback_flatters_eps",
                "detail": "Diluted share count fell 2.4%, adding roughly 2.4 points to the 24.4% EPS growth.",
                "severity": "low",
            },
        ],
        "valuation": {
            "pe": v(pe, "multiple", "fact", None, ["market.price", fpath("FY2025", "eps_diluted")]),
            "forward_pe": v(fwd_pe, "multiple", "estimate", None, ["market.price", "consensus.eps_next_fy"]),
            "ev_ebitda": v(ev_ebitda, "multiple", "fact", None, ["market.enterprise_value", "cash_flow.ebitda"]),
            "ev_revenue": v(EV / FY["revenue"], "multiple", "fact", None,
                            ["market.enterprise_value", fpath("FY2025", "revenue")]),
            "p_fcf": v(MARKET_CAP / FY["fcf"], "multiple", "fact", None, ["market.market_cap", "cash_flow.fcf"]),
            "vs_peers": {
                "pe_premium": v(pe / peer_pe_med - 1, "fraction", "fact", None, ["valuation.pe", "peers[*].pe"]),
                "ev_ebitda_premium": v(ev_ebitda / peer_eve_med - 1, "fraction", "fact", None,
                                       ["valuation.ev_ebitda", "peers[*].ev_ebitda"]),
            },
            "vs_sp500": {
                "forward_pe_premium": v(fwd_pe / SP_FWD_PE - 1, "fraction", "estimate", None,
                                        ["valuation.forward_pe", "sp500_baseline.forward_pe"]),
            },
        },
        "reverse_dcf": {
            "implied_fcf_cagr": v(base_cagr, "fraction", "fact", None,
                                  ["market.enterprise_value", "cash_flow.fcf"]),
            "assumptions": {
                "discount_rate": v(0.09, "fraction", "assumption", S_CALC),
                "terminal_growth": v(0.03, "fraction", "assumption", S_CALC),
                "horizon_years": 10,
            },
            "sensitivity_grid": grid,
        },
    }


# --------------------------------------------------------------------------
# scenarios.json + scenario_result.json
# --------------------------------------------------------------------------
SCEN = {  # revenue_cagr, terminal net margin, exit P/E, probability
    "bear": (0.03, 0.10, 16.0, 0.30),
    "base": (0.08, 0.125, 22.0, 0.50),
    "bull": (0.12, 0.14, 26.0, 0.20),
}
HORIZON = 5
SP_EXPECTED = 0.07
BASE_RATE = {"1y": 0.47, "3y": 0.44, "5y": 0.42}
REQ_SHIFT = -0.10
CAP = 0.15


def scen_numbers(k):
    g, m, pe, p = SCEN[k]
    eps = FY["revenue"] * (1 + g) ** HORIZON * m / SHARES_OUT
    target = eps * pe
    ann = (target / PRICE) ** (1 / HORIZON) - 1
    return eps, target, ann


def build_scenarios():
    quotes = {
        "bear": [{"quote": "could reduce our gross margin by up to 150 basis points", "source_id": S_RISK}],
        "base": [{"quote": "we expect revenue growth of 8% to 10% and operating margin of 16% to 17%",
                  "source_id": S_MDNA}],
        "bull": [{"quote": "Customers who adopted our software platform renewed at a rate of 94%",
                  "source_id": S_BUS}],
    }
    rationale = {
        "bear": "Bundled competitor pricing squeezes mid-market margin and the multiple compresses to 16x.",
        "base": "Management guidance is delivered; multiple de-rates from 33x to 22x as growth normalises.",
        "bull": "Software mix and switching costs sustain double-digit growth and margin expansion.",
    }
    out = {}
    for k, (g, m, pe, p) in SCEN.items():
        eps, _, _ = scen_numbers(k)
        out[k] = {
            "probability": p,
            "horizon_years": HORIZON,
            "revenue_cagr": v(g, "fraction", "assumption", S_LLM),
            "terminal_margin": v(m, "fraction", "assumption", S_LLM),
            "eps_at_horizon": v(eps, "usd_per_share", "estimate", None,
                                [f"scenarios.{k}.revenue_cagr", f"scenarios.{k}.terminal_margin",
                                 "market.shares_outstanding"]),
            "exit_multiple": v(pe, "multiple", "assumption", S_LLM),
            "rationale": rationale[k],
            "evidence": quotes[k],
        }
    return {
        "schema_version": SCHEMA_VERSION, "ticker": TICKER, "as_of": AS_OF,
        "scenarios": out,
        "prior_shift": {
            "value": REQ_SHIFT,
            "reason": "Stock trades at a 27% P/E premium to peers with decelerating guided growth.",
        },
    }


def rubric(excess):
    """MOCK rubric only; P2 owns the real one (docs/p2/rubric.md)."""
    if excess < -0.06:
        return 3
    if excess < -0.02:
        return 4
    if excess <= 0.02:
        return 5
    if excess <= 0.06:
        return 6
    return 7


def build_scenario_result():
    scen, expected = {}, 0.0
    for k, (_, _, _, p) in SCEN.items():
        _, target, ann = scen_numbers(k)
        expected += p * ann
        scen[k] = {
            "probability": p,
            "price_target": v(target, "usd_per_share", "estimate", None,
                              [f"scenarios.{k}.eps_at_horizon", f"scenarios.{k}.exit_multiple"]),
            "annualized_return": v(ann, "fraction", "estimate", None,
                                   [f"scenario_result.scenarios.{k}.price_target", "market.price"]),
        }
    excess = expected - SP_EXPECTED
    applied = max(-CAP, min(CAP, REQ_SHIFT))
    p_beat = {h: max(0.0, min(1.0, BASE_RATE[h] + applied)) for h in BASE_RATE}
    score = rubric(excess)
    return {
        "schema_version": SCHEMA_VERSION, "ticker": TICKER, "as_of": AS_OF,
        "scenarios": scen,
        "expected_annualized_return": v(expected, "fraction", "estimate", None,
                                        ["scenario_result.scenarios.*.annualized_return"]),
        "sp500_expected_return": v(SP_EXPECTED, "fraction", "assumption", S_CALC),
        "excess_vs_sp500": {
            h: v(excess, "fraction", "estimate", None,
                 ["scenario_result.expected_annualized_return", "scenario_result.sp500_expected_return"])
            for h in ("1y", "3y", "5y")
        },
        "p_beat_sp500": {h: round(p, 4) for h, p in p_beat.items()},
        "prior": {"base_rate": BASE_RATE, "requested_shift": REQ_SHIFT, "applied_shift": applied, "cap": CAP},
        "scores": {"short_term": score, "medium_term": score, "long_term": min(10, score + 1)},
        "consistency": {"ok": True, "issues": []},
    }


# --------------------------------------------------------------------------
# analyses (agent outputs), audit, verdict
# --------------------------------------------------------------------------
def analysis(agent, summary, findings):
    return {
        "schema_version": SCHEMA_VERSION, "agent": agent, "ticker": TICKER, "as_of": AS_OF,
        "model": "mock", "summary": summary, "findings": findings,
    }


def build_analyses(metrics):
    dso_now = FY["recv"] / FY["revenue"] * 365
    g = metrics["margins"]["FY2025"]["gross"]
    forensic = analysis(
        "forensic",
        "Earnings growth is mostly real (volume, price, mix) but two items flatter it: buybacks and stretched receivables.",
        [
            {"claim": "Gross margin expansion came from price and software mix; durable unless competitors' bundling forces price cuts.",
             "trend": "temporarily_positive",
             "evidence": [{"quote": "Gross margin improved to 40.0% from 38.9% as a result of price increases and a favorable product mix toward software subscriptions.",
                           "source_id": S_MDNA}],
             "numbers": [g], "confidence": "medium"},
            {"claim": "Receivables grew faster than revenue because two large customers received longer payment terms: a working-capital quality watch item.",
             "trend": "temporarily_negative",
             "evidence": [{"quote": "Accounts receivable increased to $700 million from $600 million, primarily due to longer payment terms granted to two large customers.",
                           "source_id": S_MDNA}],
             "numbers": [v(dso_now, "days", "fact", None, [fpath("FY2025", "receivables"), fpath("FY2025", "revenue")])],
             "confidence": "high"},
            {"claim": "Buybacks shrank the diluted share count 2.4%, contributing about 2.4 points of the 24.4% EPS growth.",
             "trend": "neutral",
             "evidence": [{"quote": "reduced diluted shares outstanding by 2.4%", "source_id": S_MDNA}],
             "numbers": [metrics["per_share"]["dilution_yoy"]], "confidence": "high"},
        ])
    business = analysis(
        "business",
        "Good business with real switching costs, but mid-market pricing pressure and customer concentration are live issues.",
        [
            {"claim": "Embedded sensors and a subscription platform create switching costs, shown by high renewal rates.",
             "trend": "structurally_positive",
             "evidence": [{"quote": "Customers who adopted our software platform renewed at a rate of 94% in fiscal 2025.",
                           "source_id": S_BUS}],
             "numbers": [], "confidence": "medium"},
            {"claim": "Competitor bundling in the mid-market threatens pricing and gross margin.",
             "trend": "temporarily_negative",
             "evidence": [{"quote": "could reduce our gross margin by up to 150 basis points", "source_id": S_RISK}],
             "numbers": [], "confidence": "medium"},
            {"claim": "Customer concentration raises the cost of any single contract loss.",
             "trend": "structurally_negative",
             "evidence": [{"quote": "Our largest ten customers accounted for 31% of fiscal 2025 revenue", "source_id": S_RISK}],
             "numbers": [], "confidence": "high"},
        ])
    valuation = analysis(
        "valuation",
        "At $50 the market already prices double-digit FCF growth for a decade; guidance does not support that.",
        [
            {"claim": "The current price implies about 11.6% annual FCF growth for ten years (9% discount rate, 3% terminal growth); guidance is 8-10% revenue growth.",
             "trend": "structurally_negative",
             "evidence": [{"quote": "we expect revenue growth of 8% to 10% and operating margin of 16% to 17%",
                           "source_id": S_MDNA}],
             "numbers": [metrics["reverse_dcf"]["implied_fcf_cagr"]], "confidence": "medium"},
        ])
    red = analysis(
        "red_team",
        "Even the base case underperforms the S&P; the stock is exposed to multiple compression and a 2027 refinancing.",
        [
            {"claim": "A de-rating from 33x to 22x earnings alone would cut the price about a third even if guidance is met.",
             "trend": "structurally_negative",
             "evidence": [{"quote": "we expect revenue growth of 8% to 10% and operating margin of 16% to 17%",
                           "source_id": S_MDNA}],
             "numbers": [metrics["valuation"]["pe"]], "confidence": "medium"},
            {"claim": "$400 million of debt matures in fiscal 2027 and may be refinanced on worse terms.",
             "trend": "temporarily_negative",
             "evidence": [{"quote": "of which $400 million matures in fiscal 2027", "source_id": S_RISK}],
             "numbers": [], "confidence": "low"},
        ])
    return {"forensic": forensic, "business": business, "valuation": valuation, "red_team": red}


def build_audit():
    return {
        "schema_version": SCHEMA_VERSION,
        "passed": True,
        "issues": [
            {"severity": "warn", "path": "agent_outputs.forensic.findings[2]",
             "message": "Mock warning: EPS-growth attribution (2.4 points) is derived by the agent, not by calc/."},
        ],
    }


SECTION_TITLES = [
    ("financial_quality", "1. Financial quality", "forensic"),
    ("income_statement", "2. Income statement deep dive", "forensic"),
    ("balance_sheet", "3. Balance sheet strength", "balance_sheet"),
    ("free_cash_flow", "4. Free cash flow", "balance_sheet"),
    ("management_guidance", "5. Management and guidance", "business"),
    ("competitive_position", "6. Competitive position", "business"),
    ("valuation", "7. Valuation", "valuation"),
    ("expectations_vs_reality", "8. Expectations vs reality", "valuation"),
    ("catalysts", "9. Catalysts", "business"),
    ("risks", "10. Risks", "red_team"),
    ("scenarios", "11. Bull / base / bear", "valuation"),
    ("sp500_test", "12. S&P 500 outperformance test", "valuation"),
    ("buyability", "13. Buyability score", "synthesizer"),
    ("buy_more_or_sell", "14. What would make me buy more or sell", "synthesizer"),
    ("committee_verdict", "15. Investment committee verdict", "synthesizer"),
]


def build_verdict(factsheet, metrics, analyses, sres, audit):
    expected = sres["expected_annualized_return"]
    pe_prem = metrics["valuation"]["vs_peers"]["pe_premium"]["value"]
    sections = []
    for sid, title, agent in SECTION_TITLES:
        sections.append({
            "id": sid, "title": title,
            "body_markdown": f"_Mock content for **{title}**. Real text is written by the {agent} agent._ "
                             f"ACME trades at {metrics['valuation']['pe']['value']:.1f}x trailing earnings, "
                             f"a {pe_prem*100:.0f}% premium to peers.",
            "agent": agent,
            "evidence": [analyses["forensic"]["findings"][0]["evidence"][0]] if sid == "financial_quality" else [],
        })
    return {
        "schema_version": SCHEMA_VERSION, "ticker": TICKER, "as_of": AS_OF,
        "generated_at": BUILT_AT, "mode": "mock", "disclaimer": DISCLAIMER,
        "card": {
            "company": factsheet["company_name"], "ticker": TICKER,
            "price": factsheet["market"]["price"], "market_cap": factsheet["market"]["market_cap"],
            "thesis": ("Acme is a good business with real switching costs, but at 33x earnings the market is pricing a decade "
                       "of double-digit FCF growth that guidance does not support. Even the base case trails the S&P 500 "
                       "as the multiple de-rates. Wait for a much lower price."),
            "scores": sres["scores"],
            "p_beat_sp500_5y": sres["p_beat_sp500"]["5y"],
            "expected_5y_return": expected,
            "primary_catalyst": "Software mix shift lifting gross margin above 41%.",
            "biggest_risk": "Multiple compression from 33x toward 22x even if guidance is met.",
            "valuation": "expensive", "business_quality": "good", "financial_strength": "strong",
            "verdict": "avoid",
            "ten_thousand_dollar_answer": {
                "choice": "sp500",
                "reason": "Probability-weighted return is below the S&P 500 assumption and the base case only breaks even.",
            },
        },
        "sections": sections,
        "red_team": {
            "summary": analyses["red_team"]["summary"],
            "responses_by_synthesizer": "Accepted: valuation risk is the dominant issue and drives the AVOID. "
                                        "Not accepted: the 2027 refinancing is low-risk given 13x interest coverage.",
        },
        "agent_outputs": analyses,
        "scenario_result": sres,
        "audit": audit,
        "data_quality": factsheet["data_quality"],
    }


def dump(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def main():
    factsheet = build_factsheet()
    metrics = build_metrics()
    scenarios = build_scenarios()
    sres = build_scenario_result()
    analyses = build_analyses(metrics)
    audit = build_audit()
    verdict = build_verdict(factsheet, metrics, analyses, sres, audit)

    # ---- hand-check asserts (verified by a human against the base numbers) ----
    assert round(metrics["margins"]["FY2025"]["gross"]["value"], 4) == 0.4
    assert round(metrics["margins"]["FY2025"]["operating"]["value"], 4) == 0.16
    assert round(metrics["margins"]["FY2025"]["fcf"]["value"], 4) == 0.12
    assert round(metrics["growth"]["FY2025"]["revenue_yoy"]["value"], 4) == 0.1111
    assert round(metrics["growth"]["FY2025"]["eps_yoy"]["value"], 4) == 0.2437
    assert metrics["cash_flow"]["fcf"]["value"] == 600_000_000
    assert metrics["cash_flow"]["ebitda"]["value"] == 1_000_000_000
    assert factsheet["market"]["market_cap"]["value"] == 19_750_000_000
    assert factsheet["market"]["enterprise_value"]["value"] == 19_900_000_000
    assert round(metrics["cash_flow"]["fcf_yield"]["value"], 4) == 0.0304
    assert metrics["balance_sheet"]["net_debt"]["value"] == 150_000_000
    assert round(metrics["balance_sheet"]["interest_coverage"]["value"], 3) == 13.333
    assert round(metrics["valuation"]["pe"]["value"], 2) == 33.78
    assert round(metrics["valuation"]["ev_ebitda"]["value"], 2) == 19.9
    assert round(metrics["valuation"]["vs_peers"]["pe_premium"]["value"], 4) == 0.2749
    assert round(metrics["reverse_dcf"]["implied_fcf_cagr"]["value"], 3) == 0.116
    assert abs(sum(s[3] for s in SCEN.values()) - 1.0) < 1e-9
    assert round(sres["expected_annualized_return"]["value"], 3) == -0.019
    assert sres["p_beat_sp500"]["5y"] == 0.32

    dump("factsheet.json", factsheet)
    dump("metrics.json", metrics)
    dump("scenarios.json", scenarios)
    dump("scenario_result.json", sres)
    for name, a in analyses.items():
        dump(f"analysis_{name}.json", a)
    dump("audit.json", audit)
    dump("verdict.json", verdict)
    print("wrote fixtures/mock/*.json")


if __name__ == "__main__":
    main()
