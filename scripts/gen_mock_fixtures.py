#!/usr/bin/env python3
"""Generate fixtures/mock/* for the FICTIONAL company ACME.

Run with:  make gen-mock   (coordinator only)

All derived numbers are computed here from the base reported numbers, the
hand-check asserts at the bottom pin the values a human verified, and every
fixture is validated against its pydantic contract before it is written. ACME is
not a real company; nothing here is market data.

calc/ is the authority for the real formulas - the ones here are simple
stand-ins that keep the mock internally consistent so P2 has something to check
its implementation against.

Contract v2.0.0 additions (schema/CHANGELOG.md):
  - facts.json         FinancialFact rows, including ONE RESTATED and ONE DERIVED
  - filings.json       Filing + parsed FilingSection metadata
  - market_snapshot.json / company_profile.json / peers.json
  - research_state.json          the object the report is rendered from
  - scenario_weights_clamped.json  an out-of-band weight request, clamped and recorded
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic import TypeAdapter  # noqa: E402

from schema.contracts import (  # noqa: E402
    SCHEMA_VERSION,
    STATE_VERSION,
    Analysis,
    CompanyProfile,
    Factsheet,
    Filing,
    FilingSection,
    FinancialFact,
    MarketSnapshot,
    Metrics,
    Peer,
    ResearchState,
    ScenarioResult,
    Scenarios,
    ScenarioWeights,
    Verdict,
    VerificationResult,
)
from schema.contracts.state import SECTION_OWNERS  # noqa: E402

OUT = ROOT / "fixtures" / "mock"
SEC = OUT / "sections"

TICKER = "ACME"
AS_OF = "2026-09-19"
BUILT_AT = "2026-09-19T12:00:00Z"
COMPANY = "Acme Corporation (fictional mock)"
DISCLAIMER = (
    "This is AI-generated research for educational purposes only. It is not "
    "investment advice or a recommendation to buy or sell any security."
)


def v(value, unit, type_="fact", source_id=None, derived_from=None):
    """Build a VALUE OBJECT (schema/contracts/common.py ValueObject)."""
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
        period_start="2026-04-01", period_end="2026-06-30", form="10-Q",
        filed="2026-08-05", acc="0001234567-26-000090",
        revenue=1_400_000_000, cost=830_000_000, op=235_000_000, interest=14_000_000,
        tax_rate=0.20, shares=395_000_000, da=52_000_000, ocf=230_000_000, capex=70_000_000,
        sbc=27_000_000, cash=1_000_000_000, debt=1_150_000_000, assets=6_200_000_000,
        equity=3_150_000_000, ca=2_500_000_000, cl=1_350_000_000, recv=760_000_000,
        inv=520_000_000, eps=0.45),
    "FY2025": dict(
        period_start="2025-01-01", period_end="2025-12-31", form="10-K",
        filed="2026-02-20", acc="0001234567-26-000010",
        revenue=5_000_000_000, cost=3_000_000_000, op=800_000_000, interest=60_000_000,
        tax_rate=0.20, shares=400_000_000, da=200_000_000, ocf=850_000_000, capex=250_000_000,
        sbc=100_000_000, cash=900_000_000, debt=1_200_000_000, assets=6_000_000_000,
        equity=3_000_000_000, ca=2_400_000_000, cl=1_300_000_000, recv=700_000_000,
        inv=500_000_000, eps=1.48),
    "FY2024": dict(
        period_start="2024-01-01", period_end="2024-12-31", form="10-K",
        filed="2025-02-21", acc="0001234567-25-000010",
        revenue=4_500_000_000, cost=2_750_000_000, op=675_000_000, interest=65_000_000,
        tax_rate=0.20, shares=410_000_000, da=190_000_000, ocf=700_000_000, capex=220_000_000,
        sbc=90_000_000, cash=700_000_000, debt=1_300_000_000, assets=5_500_000_000,
        equity=2_700_000_000, ca=2_100_000_000, cl=1_200_000_000, recv=600_000_000,
        inv=450_000_000, eps=1.19),
    "FY2023": dict(
        period_start="2023-01-01", period_end="2023-12-31", form="10-K",
        filed="2024-02-22", acc="0001234567-24-000010",
        revenue=4_100_000_000, cost=2_560_000_000, op=574_000_000, interest=70_000_000,
        tax_rate=0.20, shares=415_000_000, da=180_000_000, ocf=600_000_000, capex=200_000_000,
        sbc=80_000_000, cash=550_000_000, debt=1_400_000_000, assets=5_100_000_000,
        equity=2_400_000_000, ca=1_900_000_000, cl=1_100_000_000, recv=520_000_000,
        inv=420_000_000, eps=0.97),
}
for _p in PERIODS.values():
    _p["gp"] = _p["revenue"] - _p["cost"]
    _p["pretax"] = _p["op"] - _p["interest"]
    _p["ni"] = _p["pretax"] * (1 - _p["tax_rate"])
    _p["fcf"] = _p["ocf"] - _p["capex"]

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

# The one restatement in the mock: FY2024 operating cash flow was filed at
# $690M in the FY2024 10-K and restated to $700M in the FY2025 10-K. Chosen
# because it sits in no identity assert, so every pinned metric is unchanged.
FY2024_OCF_AS_FILED = 690_000_000

# Source ids
S_QUOTE = "src:market:quote"
S_PEERS = "src:market:peers"
S_SP = "src:market:sp500"
S_FRED = "src:fred:DGS10"
S_CONS = "src:market:consensus"
S_PROFILE = "src:market:profile"
S_NEWS1 = "src:news:1"
S_NEWS2 = "src:news:2"
S_CALC = "src:config:calc_assumptions"
S_LLM = "src:llm:valuation"
S_LLM_SCEN = "src:llm:scenario"

ACC10K = FY["acc"]
SECTION_FILES = {
    "business": "business.txt",
    "risk_factors": "risk_factors.txt",
    "mdna": "mdna.txt",
    "debt_note": "debt_note.txt",
    "sbc_note": "sbc_note.txt",
}
S_BUS = f"src:edgar:{ACC10K}:business"
S_RISK = f"src:edgar:{ACC10K}:risk_factors"
S_MDNA = f"src:edgar:{ACC10K}:mdna"
S_DEBT = f"src:edgar:{ACC10K}:debt_note"
S_SBC = f"src:edgar:{ACC10K}:sbc_note"


def xbrl(acc):
    return f"src:edgar:{acc}:xbrl"


def sid(item):
    """Repository key for a parsed section."""
    return f"sec:{ACC10K}:{item}"


def src(item):
    """Citation key for a parsed section (what Evidence points at)."""
    return f"src:edgar:{ACC10K}:{item}"


def section_text(item):
    return (SEC / SECTION_FILES[item]).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# facts.json - the financial truth layer (FinancialFact rows)
# --------------------------------------------------------------------------
FLOW_METRICS = {
    "revenue": ("revenue", "usd", "Revenues"),
    "net_income": ("ni", "usd", "NetIncomeLoss"),
    "op_cash_flow": ("ocf", "usd", "NetCashProvidedByUsedInOperatingActivities"),
    "capex": ("capex", "usd", "PaymentsToAcquirePropertyPlantAndEquipment"),
    "eps_diluted": ("eps", "usd_per_share", "EarningsPerShareDiluted"),
    "shares_diluted": ("shares", "shares", "WeightedAverageNumberOfDilutedSharesOutstanding"),
    # Added so every fact the mock analyses cite actually exists (docs/p3/TO_BE_FIXED.md S5).
    "cost_of_revenue": ("cost", "usd", "CostOfRevenue"),
    "gross_profit": ("gp", "usd", "GrossProfit"),
    "operating_income": ("op", "usd", "OperatingIncomeLoss"),
    "pretax_income": (
        "pretax",
        "usd",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    ),
    "depreciation_amortization": ("da", "usd", "DepreciationDepletionAndAmortization"),
    "sbc": ("sbc", "usd", "ShareBasedCompensation"),
    "interest_expense": ("interest", "usd", "InterestExpense"),
}
INSTANT_METRICS = {
    "cash": ("cash", "usd", "CashAndCashEquivalentsAtCarryingValue"),
    "total_debt": ("debt", "usd", "DebtLongtermAndShorttermCombinedAmount"),
    "receivables": ("recv", "usd", "AccountsReceivableNetCurrent"),
    "inventory": ("inv", "usd", "InventoryNet"),
    "current_assets": ("ca", "usd", "AssetsCurrent"),
    "current_liabilities": ("cl", "usd", "LiabilitiesCurrent"),
    "total_assets": ("assets", "usd", "Assets"),
    "total_equity": ("equity", "usd", "StockholdersEquity"),
}


def fact_id(metric, period, suffix=None):
    base = f"fact:{TICKER}:{metric}:{period}"
    return f"{base}:{suffix}" if suffix else base


def reported_fact(metric, period, p, key, unit, concept, *, instant):
    """One as-reported XBRL fact."""
    return {
        "fact_id": fact_id(metric, period),
        "company_id": TICKER,
        "metric": metric,
        "xbrl_concept": concept,
        "value": float(p[key]),
        "unit": unit,
        "currency": "USD" if unit.startswith("usd") else None,
        "scale": "units",
        "period_type": "instant" if instant else "duration",
        "period_start": None if instant else p["period_start"],
        "period_end": p["period_end"],
        "fiscal_period": period,
        "dimension": None,
        "filing_type": p["form"],
        "accession_number": p["acc"],
        "filed_at": p["filed"],
        "retrieved_at": BUILT_AT,
        "source_url": None,
        "source_location": f"xbrl:{concept}",
        "source_kind": "xbrl_reported",
        "derivation": None,
        "superseded_by": None,
    }


def build_facts():
    facts = []
    for period, p in PERIODS.items():
        for metric, (key, unit, concept) in FLOW_METRICS.items():
            facts.append(reported_fact(metric, period, p, key, unit, concept, instant=False))
        for metric, (key, unit, concept) in INSTANT_METRICS.items():
            facts.append(reported_fact(metric, period, p, key, unit, concept, instant=True))

    # The restated fact. The current FY2024 op_cash_flow was corrected upward by
    # the FY2025 10-K, so the as-filed row is superseded and must never be cited.
    current = next(f for f in facts if f["fact_id"] == fact_id("op_cash_flow", "FY2024"))
    current["accession_number"] = ACC10K
    current["filed_at"] = FY["filed"]
    current["source_location"] = "xbrl:NetCashProvidedByUsedInOperatingActivities:restated"

    as_filed = dict(current)
    as_filed.update({
        "fact_id": fact_id("op_cash_flow", "FY2024", "as-filed"),
        "value": float(FY2024_OCF_AS_FILED),
        "accession_number": FY_PRIOR["acc"],
        "filed_at": FY_PRIOR["filed"],
        "source_location": "xbrl:NetCashProvidedByUsedInOperatingActivities",
        "superseded_by": current["fact_id"],
    })
    facts.append(as_filed)

    # The derived fact. FCF is computed by calc/, never reported by the filer.
    facts.append({
        "fact_id": fact_id("fcf", "FY2025"),
        "company_id": TICKER,
        "metric": "fcf",
        "xbrl_concept": None,
        "value": float(FY["fcf"]),
        "unit": "usd",
        "currency": "USD",
        "scale": "units",
        "period_type": "duration",
        "period_start": FY["period_start"],
        "period_end": FY["period_end"],
        "fiscal_period": "FY2025",
        "dimension": None,
        "filing_type": None,
        "accession_number": None,
        "filed_at": None,
        "retrieved_at": BUILT_AT,
        "source_url": None,
        "source_location": None,
        "source_kind": "derived",
        "derivation": {
            "formula": "op_cash_flow - capex",
            "input_fact_ids": [
                fact_id("op_cash_flow", "FY2025"),
                fact_id("capex", "FY2025"),
            ],
            "computed_by": "calc",
        },
        "superseded_by": None,
    })
    return facts


# --------------------------------------------------------------------------
# filings.json / sections
# --------------------------------------------------------------------------
def build_sections():
    """Parsed section metadata. Text is served separately, never inlined."""
    headings = {
        "business": ["Part I", "Item 1. Business"],
        "risk_factors": ["Part I", "Item 1A. Risk Factors"],
        "mdna": ["Part II", "Item 7. Management's Discussion and Analysis"],
        "debt_note": ["Part II", "Item 8. Financial Statements", "Note 9. Debt"],
        "sbc_note": ["Part II", "Item 8. Financial Statements", "Note 14. Stock-Based Compensation"],
    }
    out = []
    for item in SECTION_FILES:
        n = len(section_text(item))
        out.append({
            "section_id": sid(item),
            "source_id": src(item),
            "accession": ACC10K,
            "company_id": TICKER,
            "form": "10-K",
            "fiscal_period": "FY2025",
            "filed_at": FY["filed"],
            "item": item,
            "heading_path": headings[item],
            "char_start": 0,
            "char_end": n,
            "char_count": n,
            "text": "",
        })
    return out


def build_filings(sections):
    return [
        {
            "accession": p["acc"],
            "company_id": TICKER,
            "cik": "0001234567",
            "form": p["form"],
            "fiscal_period": period,
            "period_end": p["period_end"],
            "filed_at": p["filed"],
            "retrieved_at": BUILT_AT,
            "source_url": f"https://example.invalid/edgar/{p['acc']}.htm",
            "section_ids": [s["section_id"] for s in sections] if p["acc"] == ACC10K else [],
        }
        for period, p in PERIODS.items()
    ]


# --------------------------------------------------------------------------
# market / profile / peers
# --------------------------------------------------------------------------
def build_market_snapshot():
    return {
        "ticker": TICKER,
        "as_of": BUILT_AT,
        "retrieved_at": BUILT_AT,
        "source_id": S_QUOTE,
        "price": v(PRICE, "usd_per_share", "fact", S_QUOTE),
        "shares_outstanding": v(SHARES_OUT, "shares", "fact", S_QUOTE),
        "market_cap": v(MARKET_CAP, "usd", "fact", S_QUOTE),
        "total_debt": v(LATEST_BS["debt"], "usd", "fact", xbrl(LATEST_BS["acc"])),
        "cash": v(LATEST_BS["cash"], "usd", "fact", xbrl(LATEST_BS["acc"])),
        "enterprise_value": v(
            EV, "usd", "fact", None,
            ["market.market_cap", "financials.Q2-2026.total_debt", "financials.Q2-2026.cash"]),
        "currency": "USD",
    }


def build_company_profile():
    return {
        "ticker": TICKER,
        "company_name": COMPANY,
        "cik": "0001234567",
        "sic": "3823",
        "sic_description": "Industrial instruments for measurement and control (fictional)",
        "exchange": "MOCK",
        "fiscal_year_end": "12-31",
        "as_of": AS_OF,
        "retrieved_at": BUILT_AT,
        "source_id": S_PROFILE,
    }


PEERS_RAW = [
    ("PRAA", "Peer Alpha (mock)", 12e9, 22.0, 14.0, 2.5, 0.045),
    ("PRBB", "Peer Beta (mock)", 30e9, 25.0, 15.0, 3.0, 0.040),
    ("PRCC", "Peer Gamma (mock)", 18e9, 28.0, 16.0, 3.2, 0.038),
    ("PRDD", "Peer Delta (mock)", 25e9, 30.0, 18.0, 3.6, 0.033),
]


def build_peers():
    return [
        {
            "ticker": t,
            "company_name": name,
            "sic": "3823",
            "market_cap": v(mc, "usd", "fact", S_PEERS),
            "pe": v(pe, "multiple", "fact", S_PEERS),
            "ev_ebitda": v(eve, "multiple", "fact", S_PEERS),
            "ev_revenue": v(evr, "multiple", "fact", S_PEERS),
            "fcf_yield": v(fy, "fraction", "fact", S_PEERS),
            "selection_reason": "Same SIC code and within one order of magnitude on market cap.",
        }
        for t, name, mc, pe, eve, evr, fy in PEERS_RAW
    ]


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


# --------------------------------------------------------------------------
# factsheet.json
# --------------------------------------------------------------------------
def fin_entry(label, p):
    s = xbrl(p["acc"])
    # FY2024 operating cash flow is the RESTATED value, so it cites the filing
    # that restated it rather than the one that originally reported it.
    ocf_source = xbrl(ACC10K) if label == "FY2024" else s
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
        "op_cash_flow": v(p["ocf"], "usd", "fact", ocf_source),
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


def build_factsheet(sections, peers, market):
    sources = {}
    for p in PERIODS.values():
        sources[xbrl(p["acc"])] = {
            "kind": "edgar_xbrl", "url": None, "accession": p["acc"], "fetched_at": BUILT_AT}
    for item in SECTION_FILES:
        sources[src(item)] = {
            "kind": "edgar_text", "url": None, "accession": ACC10K, "fetched_at": BUILT_AT}
    for s, kind in ((S_QUOTE, "market"), (S_PEERS, "market"), (S_SP, "market"),
                    (S_CONS, "market"), (S_PROFILE, "market"), (S_FRED, "fred"),
                    (S_NEWS1, "news"), (S_NEWS2, "news")):
        sources[s] = {"kind": kind, "url": None, "accession": None, "fetched_at": BUILT_AT}
    return {
        "schema_version": SCHEMA_VERSION,
        "ticker": TICKER,
        "company_name": COMPANY,
        "as_of": AS_OF,
        "built_at": BUILT_AT,
        "mode": "mock",
        "scope": {"in_scope": True, "reason": None},
        "data_quality": {"overall": "ok", "gaps": []},
        "market": market,
        "financials": [fin_entry(k, p) for k, p in PERIODS.items()],
        "peers": peers,
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
        "filing_sections": sections,
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


def reverse_dcf_solve(r, tg, ev=EV, fcf0=None, n=10):
    fcf0 = FY["fcf"] if fcf0 is None else fcf0

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
        # `label=label` binds the loop variable: without it every lambda would
        # close over the LAST label and every margin would cite FY2023.
        d = lambda f, label=label: [fpath(label, f)]  # noqa: E731
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
    peer_pe_med = median([x[3] for x in PEERS_RAW])
    peer_eve_med = median([x[4] for x in PEERS_RAW])
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
            {
                "flag": "restated_prior_period",
                "detail": "FY2024 operating cash flow was restated from $690M to $700M by the FY2025 10-K.",
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
SCEN = {  # revenue_cagr, terminal net margin, exit P/E, requested probability
    "bear": (0.03, 0.10, 16.0, 0.30),
    "base": (0.08, 0.125, 22.0, 0.50),
    "bull": (0.12, 0.14, 26.0, 0.20),
}
HORIZON_YEARS = 5
SP_EXPECTED = 0.07
BASE_RATE = {"short_term": 0.47, "medium_term": 0.44, "long_term": 0.42}
REQ_SHIFT = -0.10
CAP = 0.15

# calc/config.py owns the live values; these mirror them so the mock is consistent.
DEFAULT_WEIGHTS = {"bear": 0.30, "base": 0.50, "bull": 0.20}
WEIGHT_BAND = 0.15


def scen_numbers(k):
    g, m, pe, _ = SCEN[k]
    eps = FY["revenue"] * (1 + g) ** HORIZON_YEARS * m / SHARES_OUT
    target = eps * pe
    ann = (target / PRICE) ** (1 / HORIZON_YEARS) - 1
    return eps, target, ann


def bound_weights(requested):
    """Clamp each requested weight into its band, then redistribute the residual.

    This is the algorithm calc.evaluate_scenarios must implement (docs/pipeline.md).
    Residual goes to the UNCLAMPED weights in proportion, so every applied weight
    stays inside its band instead of being pushed back out by renormalization.
    """
    clamped, was_clamped = {}, {}
    for name, req in requested.items():
        lo = DEFAULT_WEIGHTS[name] - WEIGHT_BAND
        hi = DEFAULT_WEIGHTS[name] + WEIGHT_BAND
        clamped[name] = min(hi, max(lo, req))
        was_clamped[name] = abs(clamped[name] - req) > 1e-9

    residual = 1.0 - sum(clamped.values())
    free = {n: w for n, w in clamped.items() if not was_clamped[n]}
    applied = dict(clamped)
    if abs(residual) > 1e-12 and free:
        total_free = sum(free.values())
        for name, weight in free.items():
            applied[name] = weight + residual * (weight / total_free)

    clamps = []
    for name in ("bear", "base", "bull"):
        clamps.append({
            "scenario": name,
            "requested": round(requested[name], 10),
            "clamped_to": round(clamped[name], 10),
            "applied": round(applied[name], 10),
            "default_weight": DEFAULT_WEIGHTS[name],
            "band": WEIGHT_BAND,
            "was_clamped": was_clamped[name],
            "was_renormalized": abs(applied[name] - clamped[name]) > 1e-9,
            "reason": WEIGHT_REASONS[name],
        })
    return {
        "bear": round(applied["bear"], 10),
        "base": round(applied["base"], 10),
        "bull": round(applied["bull"], 10),
        "clamps": clamps,
        "any_clamped": any(c["was_clamped"] for c in clamps),
        "renormalized": any(c["was_renormalized"] for c in clamps),
    }


WEIGHT_REASONS = {
    "bear": "Competitor bundling is already visible in the mid-market risk disclosure.",
    "base": "Management guidance has been met in each of the last three years.",
    "bull": "Software mix shift would have to accelerate beyond the guided range.",
}


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
            "probability_rationale": WEIGHT_REASONS[k],
            "horizon_years": HORIZON_YEARS,
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
            "source": "scenario",
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
    weights = bound_weights({k: SCEN[k][3] for k in SCEN})
    scen, expected = {}, 0.0
    for k in SCEN:
        _, target, ann = scen_numbers(k)
        w = weights[k]
        expected += w * ann
        scen[k] = {
            "probability": w,
            "price_target": v(target, "usd_per_share", "estimate", None,
                              [f"scenarios.{k}.eps_at_horizon", f"scenarios.{k}.exit_multiple"]),
            "annualized_return": v(ann, "fraction", "estimate", None,
                                   [f"scenario_result.scenarios.{k}.price_target", "market.price"]),
        }
    excess = expected - SP_EXPECTED
    applied = max(-CAP, min(CAP, REQ_SHIFT))
    p_beat = {h: round(max(0.0, min(1.0, BASE_RATE[h] + applied)), 4) for h in BASE_RATE}
    score = rubric(excess)

    def excess_vo():
        return v(excess, "fraction", "estimate", None,
                 ["scenario_result.expected_annualized_return", "scenario_result.sp500_expected_return"])

    horizons = ("short_term", "medium_term", "long_term")
    return {
        "schema_version": SCHEMA_VERSION, "ticker": TICKER, "as_of": AS_OF,
        "scenarios": scen,
        "weights": weights,
        "expected_annualized_return": v(expected, "fraction", "estimate", None,
                                        ["scenario_result.scenarios.*.annualized_return",
                                         "scenario_result.weights"]),
        "sp500_expected_return": v(SP_EXPECTED, "fraction", "assumption", S_CALC),
        "expected_return_vs_sp500": {h: excess_vo() for h in horizons},
        "excess_vs_sp500": {h: excess_vo() for h in horizons},
        "p_beat_sp500": p_beat,
        "prior": {
            "base_rate": BASE_RATE,
            "requested_shift": REQ_SHIFT,
            "applied_shift": applied,
            "cap": CAP,
            "shift_reasons": [
                "scenario: stock trades at a 27% P/E premium to peers with decelerating guided growth.",
            ],
        },
        "scores": {"short_term": score, "medium_term": score, "long_term": min(10, score + 1)},
        "consistency": {"ok": True, "issues": []},
    }


def build_clamped_weights():
    """A SEPARATE fixture proving an out-of-band request is clamped AND recorded.

    ACME's own scenario_result uses in-band weights so its pinned numbers do not
    move. This fixture is the counter-example the contract tests assert on:
    the Scenario Agent asks for bear=0.55 (band tops out at 0.45), code clamps it
    and redistributes the residual to the untouched weights.
    """
    return bound_weights({"bear": 0.55, "base": 0.30, "bull": 0.15})


# --------------------------------------------------------------------------
# analyses (agent outputs), audit, research state, verdict
# --------------------------------------------------------------------------
def analysis(agent, summary, findings):
    return {
        "schema_version": SCHEMA_VERSION, "agent": agent, "ticker": TICKER, "as_of": AS_OF,
        "model": "mock", "summary": summary, "findings": findings,
    }


def build_analyses(metrics):
    dso_now = FY["recv"] / FY["revenue"] * 365
    g = metrics["margins"]["FY2025"]["gross"]
    financial = analysis(
        "financial",
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
            {"claim": "Buybacks shrank the diluted share count, contributing part of reported EPS growth rather than operating improvement.",
             "trend": "neutral",
             "evidence": [{"quote": "reduced diluted shares outstanding by 2.4%", "source_id": S_MDNA}],
             "numbers": [metrics["per_share"]["dilution_yoy"]], "confidence": "high"},
            {"claim": "Management presents non-GAAP operating income excluding a recurring stock compensation expense.",
             "trend": "structurally_negative",
             "evidence": [{"quote": "stock-based compensation is a recurring expense and that our non-GAAP measures should not be considered in isolation",
                           "source_id": S_SBC}],
             "numbers": [metrics["per_share"]["sbc_pct_revenue"]], "confidence": "high"},
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
            {"claim": "The current price implies roughly double-digit annual FCF growth for a decade at a nine percent discount rate; guidance implies less.",
             "trend": "structurally_negative",
             "evidence": [{"quote": "we expect revenue growth of 8% to 10% and operating margin of 16% to 17%",
                           "source_id": S_MDNA}],
             "numbers": [metrics["reverse_dcf"]["implied_fcf_cagr"]], "confidence": "medium"},
        ])
    red = analysis(
        "red_team",
        "Even the base case underperforms the S&P; the stock is exposed to multiple compression and a 2027 refinancing.",
        [
            {"claim": "A de-rating toward the peer median alone would cut the price by roughly a third even if guidance is met.",
             "trend": "structurally_negative",
             "evidence": [{"quote": "we expect revenue growth of 8% to 10% and operating margin of 16% to 17%",
                           "source_id": S_MDNA}],
             "numbers": [metrics["valuation"]["pe"]], "confidence": "medium"},
            {"claim": "Senior notes mature in fiscal 2027 and may be refinanced on worse terms.",
             "trend": "temporarily_negative",
             "evidence": [{"quote": "consisting of $400 million of 4.25% senior notes due fiscal 2027",
                           "source_id": S_DEBT}],
             "numbers": [], "confidence": "low"},
        ])
    return {"financial": financial, "business": business, "valuation": valuation, "red_team": red}


def build_audit():
    return {
        "schema_version": SCHEMA_VERSION,
        "passed": True,
        "issues": [
            {
                "issue_type": "recompute_mismatch",
                "severity": "warn",
                "path": "sections.earnings_quality",
                "message": "Mock warning: EPS-growth attribution was rounded by the agent rather "
                           "than recomputed by calc/.",
                "claim_id": "claim:financial:buyback-eps",
                "expected": "2.44 points of the 24.37% EPS growth",
                "actual": "about 2.4 points",
                "checked_by_llm": False,
            },
        ],
        "claims_checked": 16,
        "claims_verified": 16,
        "claims_unverified": 0,
        "llm_checks_run": 4,
        "retries_issued": [],
    }


def claim(cid, text, *, value=None, facts=(), sections=(), evidence=(), by="agent",
          trend="neutral", confidence="medium", status="verified"):
    return {
        "claim_id": cid,
        "text": text,
        "value": value,
        "fact_ids": list(facts),
        "section_ids": list(sections),
        "evidence": list(evidence),
        "derived_by": by,
        "trend": trend,
        "confidence": confidence,
        "verification_status": status,
    }


def build_research_state(metrics, sres, audit, analyses):
    f = fact_id
    titles = {
        "company": "Company",
        "financials": "Financial quality",
        "balance_sheet": "Balance sheet strength",
        "cash_flow": "Free cash flow",
        "earnings_quality": "Earnings quality",
        "management": "Management and guidance",
        "competitive_position": "Competitive position",
        "valuation": "Valuation",
        "expectations": "Expectations vs reality",
        "catalysts": "Catalysts",
        "risks": "Risks",
        "scenarios": "Bull / base / bear",
        "sp500_comparison": "S&P 500 outperformance test",
        "decision": "Investment committee verdict",
    }
    claims = {
        "company": [claim(
            "claim:business:profile",
            "Acme designs and sells industrial sensors and monitoring software to manufacturers.",
            sections=[sid("business")], by="filing_text",
            evidence=[{"quote": "Acme Corporation designs and sells industrial sensors and monitoring software to manufacturers",
                       "source_id": S_BUS}])],
        "financials": [claim(
            "claim:financial:revenue",
            "Gross margin was 40.0% of revenue in the latest full year.",
            value=metrics["margins"]["FY2025"]["gross"],
            facts=[f("gross_profit", "FY2025"), f("revenue", "FY2025")],
            by="code", trend="structurally_positive")],
        "balance_sheet": [claim(
            "claim:financial:net-debt",
            "Net debt is small relative to earnings, leaving the balance sheet unstressed.",
            value=metrics["balance_sheet"]["net_debt"],
            facts=[f("total_debt", "Q2-2026"), f("cash", "Q2-2026")], by="code")],
        "cash_flow": [claim(
            "claim:financial:fcf",
            "Free cash flow is derived from operating cash flow less capital expenditure.",
            value=metrics["cash_flow"]["fcf"], facts=[f("fcf", "FY2025")], by="code",
            trend="structurally_positive")],
        "earnings_quality": [
            claim("claim:financial:buyback-eps",
                  "Buybacks shrank the diluted share count, flattering reported EPS growth.",
                  value=metrics["per_share"]["dilution_yoy"],
                  facts=[f("shares_diluted", "FY2025"), f("shares_diluted", "FY2024")],
                  sections=[sid("mdna")], by="code",
                  evidence=[{"quote": "reduced diluted shares outstanding by 2.4%", "source_id": S_MDNA}]),
            claim("claim:financial:restated-ocf",
                  "Prior-year operating cash flow was restated upward by the latest annual filing.",
                  facts=[f("op_cash_flow", "FY2024"), f("op_cash_flow", "FY2024", "as-filed")],
                  by="code", trend="neutral"),
            claim("claim:financial:non-gaap",
                  "Management excludes a recurring stock compensation expense from its non-GAAP operating income.",
                  sections=[sid("sbc_note")], by="agent", trend="structurally_negative",
                  evidence=[{"quote": "stock-based compensation is a recurring expense and that our non-GAAP measures should not be considered in isolation",
                             "source_id": S_SBC}]),
        ],
        "management": [claim(
            "claim:business:guidance",
            "Management has issued explicit forward guidance for revenue growth and operating margin.",
            sections=[sid("mdna")], by="agent",
            evidence=[{"quote": "we expect revenue growth of 8% to 10% and operating margin of 16% to 17%",
                       "source_id": S_MDNA}])],
        "competitive_position": [claim(
            "claim:business:switching-costs",
            "Embedded sensors and a subscription platform create switching costs, shown by a high renewal rate.",
            sections=[sid("business")], by="agent", trend="structurally_positive",
            evidence=[{"quote": "Customers who adopted our software platform renewed at a rate of 94% in fiscal 2025.",
                       "source_id": S_BUS}])],
        "valuation": [claim(
            "claim:valuation:pe-premium",
            "The shares trade at a premium to the peer median on trailing earnings.",
            value=metrics["valuation"]["vs_peers"]["pe_premium"],
            facts=[f("eps_diluted", "FY2025")], by="code", trend="structurally_negative")],
        "expectations": [claim(
            "claim:valuation:implied-growth",
            "The current price implies faster free cash flow growth than management guides to.",
            value=metrics["reverse_dcf"]["implied_fcf_cagr"], facts=[f("fcf", "FY2025")],
            sections=[sid("mdna")], by="code", trend="structurally_negative",
            evidence=[{"quote": "we expect revenue growth of 8% to 10% and operating margin of 16% to 17%",
                       "source_id": S_MDNA}])],
        "catalysts": [claim(
            "claim:business:mix-shift",
            "A continued shift toward software subscriptions would lift gross margin further.",
            sections=[sid("mdna")], by="agent", trend="temporarily_positive",
            evidence=[{"quote": "a favorable product mix toward software subscriptions", "source_id": S_MDNA}])],
        "risks": [
            claim("claim:red-team:bundling",
                  "Competitor bundling in the mid-market could force price cuts and compress gross margin.",
                  sections=[sid("risk_factors")], by="agent", trend="structurally_negative",
                  evidence=[{"quote": "could reduce our gross margin by up to 150 basis points",
                             "source_id": S_RISK}]),
            claim("claim:red-team:refinancing",
                  "Senior notes mature in fiscal 2027 and may be refinanced on worse terms.",
                  sections=[sid("debt_note")], by="agent", trend="temporarily_negative",
                  confidence="low",
                  evidence=[{"quote": "consisting of $400 million of 4.25% senior notes due fiscal 2027",
                             "source_id": S_DEBT}]),
        ],
        "scenarios": [claim(
            "claim:scenario:weights",
            "Scenario weights were proposed by the agent and bounded by code before use.",
            by="code", trend="neutral")],
        "sp500_comparison": [claim(
            "claim:scenario:excess",
            "The probability-weighted expected return trails the assumed index return.",
            value=sres["expected_annualized_return"], facts=[f("fcf", "FY2025")], by="code",
            trend="structurally_negative")],
        "decision": [claim(
            "claim:synthesizer:verdict",
            "The business is sound but the price already discounts more growth than guidance supports, so the committee avoids the shares.",
            by="agent", sections=[sid("mdna")], trend="structurally_negative",
            evidence=[{"quote": "we expect revenue growth of 8% to 10% and operating margin of 16% to 17%",
                       "source_id": S_MDNA}])],
    }
    sections = {
        key: {
            "section_key": key,
            "title": titles[key],
            "owner": owner,
            "claims": claims[key],
            "verification_status": "verified",
            "retry_count": 0,
        }
        for key, owner in SECTION_OWNERS.items()
    }
    return {
        "state_version": STATE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "ticker": TICKER,
        "as_of": AS_OF,
        "created_at": BUILT_AT,
        "mode": "mock",
        "sections": sections,
        "agent_outputs": analyses,
        "scenario_result": sres,
        "verification": audit,
        "data_quality": {"overall": "ok", "gaps": []},
        "redacted": False,
    }


def build_verdict(factsheet, metrics, analyses, sres, audit, state):
    pe_prem = metrics["valuation"]["vs_peers"]["pe_premium"]["value"]
    sections = []
    for key, section in state["sections"].items():
        sections.append({
            "id": key,
            "title": section["title"],
            "body_markdown": f"_Mock content for **{section['title']}**, rendered from "
                             f"{len(section['claims'])} claim(s) owned by the "
                             f"{section['owner']} agent._ ACME trades at "
                             f"{metrics['valuation']['pe']['value']:.1f}x trailing earnings, a "
                             f"{pe_prem * 100:.0f}% premium to peers.",
            "agent": section["owner"],
            "evidence": [e for c in section["claims"] for e in c["evidence"]][:1],
            "verification_status": section["verification_status"],
            "unverified_claim_ids": [],
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
            "p_beat_sp500_5y": sres["p_beat_sp500"]["long_term"],
            "expected_5y_return": sres["expected_annualized_return"],
            "expected_return_vs_sp500": sres["expected_return_vs_sp500"],
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
            "drawdown_path": "A de-rating to the peer median combined with a single large contract loss.",
            "requested_prior_shift": None,
        },
        "agent_outputs": analyses,
        "scenario_result": sres,
        "audit": audit,
        "data_quality": factsheet["data_quality"],
        "metrics_ref": "fixtures/mock/metrics.json",
        "state_version": STATE_VERSION,
    }


# --------------------------------------------------------------------------
# write + validate
# --------------------------------------------------------------------------
def dump(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    sections = build_sections()
    peers = build_peers()
    market = build_market_snapshot()
    profile = build_company_profile()
    facts = build_facts()
    filings = build_filings(sections)

    factsheet = build_factsheet(sections, peers, market)
    metrics = build_metrics()
    scenarios = build_scenarios()
    sres = build_scenario_result()
    clamped = build_clamped_weights()
    analyses = build_analyses(metrics)
    audit = build_audit()
    state = build_research_state(metrics, sres, audit, analyses)
    verdict = build_verdict(factsheet, metrics, analyses, sres, audit, state)

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
    # ACME's own weights are all in band, so the pinned expected return is unchanged.
    assert sres["weights"]["any_clamped"] is False
    assert (sres["weights"]["bear"], sres["weights"]["base"], sres["weights"]["bull"]) == (0.3, 0.5, 0.2)
    assert round(sres["expected_annualized_return"]["value"], 3) == -0.019
    assert sres["p_beat_sp500"]["long_term"] == 0.32
    # The clamp fixture: bear was asked for at 0.55 and bounded to 0.45.
    assert clamped["any_clamped"] is True
    assert clamped["bear"] == 0.45
    assert abs(clamped["bear"] + clamped["base"] + clamped["bull"] - 1.0) < 1e-9
    # Exactly one restated and one derived fact.
    assert sum(1 for x in facts if x["superseded_by"]) == 1
    assert sum(1 for x in facts if x["source_kind"] == "derived") == 1

    # ---- validate every fixture against its pydantic contract before writing ----
    fact_list = TypeAdapter(list[FinancialFact])
    filing_list = TypeAdapter(list[Filing])
    section_list = TypeAdapter(list[FilingSection])
    peer_list = TypeAdapter(list[Peer])

    fact_list.validate_python(facts)
    filing_list.validate_python(filings)
    section_list.validate_python(sections)
    peer_list.validate_python(peers)
    MarketSnapshot.model_validate(market)
    CompanyProfile.model_validate(profile)
    Factsheet.model_validate(factsheet)
    Metrics.model_validate(metrics)
    Scenarios.model_validate(scenarios)
    ScenarioResult.model_validate(sres)
    ScenarioWeights.model_validate(clamped)
    for a in analyses.values():
        Analysis.model_validate(a)
    VerificationResult.model_validate(audit)
    ResearchState.model_validate(state)
    Verdict.model_validate(verdict)

    dump("facts.json", facts)
    dump("filings.json", filings)
    dump("market_snapshot.json", market)
    dump("company_profile.json", profile)
    dump("peers.json", peers)
    dump("factsheet.json", factsheet)
    dump("metrics.json", metrics)
    dump("scenarios.json", scenarios)
    dump("scenario_result.json", sres)
    dump("scenario_weights_clamped.json", clamped)
    for name, a in analyses.items():
        dump(f"analysis_{name}.json", a)
    dump("audit.json", audit)
    dump("research_state.json", state)
    dump("verdict.json", verdict)
    print(f"wrote fixtures/mock/*.json ({len(list(OUT.glob('*.json')))} files), all contract-valid")


if __name__ == "__main__":
    main()
