"""Export real SEC data plus calc/'s own numbers, with a source link per figure.

    python -m backtest.demo_data AAPL NVDA MSFT KO JPM

No network and no LLM: the factsheets are the recordings in `fixtures/real/`, and
everything derived comes from `calc.api`. Writes
`web/public/demo/data/<TICKER>.json` plus an `index.json`.

Every number carries `source` - the accession and the SEC URL behind it - because
a figure a reader cannot trace is a figure they have to take on trust.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / "fixtures" / "real"
OUT = ROOT / "web" / "public" / "demo" / "data"

LINE_ITEMS = [
    ("revenue", "Revenue"),
    ("gross_profit", "Gross profit"),
    ("operating_income", "Operating income"),
    ("net_income", "Net income"),
    ("eps_diluted", "Diluted EPS"),
    ("shares_diluted", "Diluted shares"),
    ("op_cash_flow", "Operating cash flow"),
    ("capex", "Capex"),
    ("sbc", "Stock compensation"),
    ("cash", "Cash"),
    ("total_debt", "Total debt"),
    ("total_equity", "Total equity"),
]

MULTIPLES = [
    ("pe", "P/E"),
    ("p_s", "P/S"),
    ("p_fcf", "P/FCF"),
    ("p_b", "P/B"),
    ("ev_ebitda", "EV/EBITDA"),
    ("ev_revenue", "EV/Revenue"),
]


def _sources(factsheet: dict) -> dict:
    return factsheet.get("sources") or {}


def _source_of(vo: dict | None, factsheet: dict, accession: str | None = None) -> dict | None:
    """The accession and SEC URL behind one ValueObject."""
    if not isinstance(vo, dict):
        return None
    source_id = vo.get("source_id")
    entry = _sources(factsheet).get(source_id) if source_id else None
    if entry is None and accession:
        entry = next(
            (e for e in _sources(factsheet).values() if e.get("accession") == accession), None
        )
    if entry is None:
        return {"accession": accession, "url": vo.get("source_url"), "source_id": source_id}
    return {
        "accession": entry.get("accession") or accession,
        "url": entry.get("url") or vo.get("source_url"),
        "source_id": source_id,
        "kind": entry.get("kind"),
    }


def _cell(vo: dict | None, factsheet: dict, accession: str | None = None) -> dict:
    ok = isinstance(vo, dict) and vo.get("status") == "ok"
    return {
        "value": vo.get("value") if ok else None,
        "unit": (vo or {}).get("unit"),
        "status": (vo or {}).get("status", "unavailable"),
        "reason": (vo or {}).get("unavailable_reason"),
        "not_applicable": bool((vo or {}).get("not_applicable")),
        "source": _source_of(vo, factsheet, accession) if ok else None,
    }


def _metric_cell(vo: dict | None, paths: bool = True) -> dict:
    ok = isinstance(vo, dict) and vo.get("status") == "ok"
    return {
        "value": vo.get("value") if ok else None,
        "unit": (vo or {}).get("unit"),
        "status": (vo or {}).get("status", "unavailable"),
        "reason": (vo or {}).get("unavailable_reason"),
        "not_applicable": bool((vo or {}).get("not_applicable")),
        "basis": (vo or {}).get("basis"),
        "derived_from": (vo or {}).get("derived_from") if paths else None,
        "fact_id": (vo or {}).get("fact_id"),
    }


def export(ticker: str) -> dict:
    from calc.api import calculate_valuation

    factsheet = json.loads((REAL / ticker / "factsheet.json").read_text(encoding="utf-8"))
    response = calculate_valuation(
        {"ticker": ticker, "methods": ["all"], "factsheet": factsheet}
    )
    metrics = response["metrics"]
    valuation = metrics["valuation"]
    market = factsheet.get("market") or {}

    periods = [p["period"] for p in factsheet["financials"]]
    financials = {
        "periods": periods,
        "filed": {p["period"]: p.get("filed_date") for p in factsheet["financials"]},
        "form": {p["period"]: p.get("form") for p in factsheet["financials"]},
        "accession": {p["period"]: p.get("accession") for p in factsheet["financials"]},
        "rows": [
            {
                "key": key,
                "label": label,
                "cells": {
                    p["period"]: _cell(p.get(key), factsheet, p.get("accession"))
                    for p in factsheet["financials"]
                },
            }
            for key, label in LINE_ITEMS
        ],
    }

    ttm = factsheet.get("ttm") or {}
    annual = metrics["latest_annual_period"]
    return {
        "ticker": ticker,
        "company_name": factsheet.get("company_name"),
        "as_of": factsheet["as_of"],
        "scope": factsheet.get("scope"),
        "scope_level": metrics.get("scope_level"),
        "data_quality": factsheet.get("data_quality"),
        "latest_annual_period": annual,
        "latest_balance_period": metrics["latest_balance_period"],
        "market": {
            "price": _cell(market.get("price"), factsheet),
            "market_cap": _cell(market.get("market_cap"), factsheet),
            "enterprise_value": _cell(market.get("enterprise_value"), factsheet),
            "shares_outstanding": _cell(market.get("shares_outstanding"), factsheet),
            "as_of": market.get("as_of"),
        },
        "financials": financials,
        "ttm": {
            field: _cell(vo, factsheet) for field, vo in ttm.items()
        }
        or None,
        "metrics": {
            "margins": {
                period: {
                    name: _metric_cell(block.get(name))
                    for name in ("gross", "operating", "net", "fcf")
                }
                for period, block in metrics["margins"].items()
            },
            "growth": {
                period: {
                    name: _metric_cell(block.get(name))
                    for name in ("revenue_yoy", "net_income_yoy", "eps_yoy", "fcf_yoy")
                }
                for period, block in metrics["growth"].items()
            },
            "cagr": {
                key: _metric_cell(metrics["cagr"].get(key))
                for key in ("revenue", "net_income", "eps_diluted", "fcf")
                if isinstance(metrics["cagr"].get(key), dict)
            }
            | {
                "years": metrics["cagr"].get("years"),
                "from_period": metrics["cagr"].get("from_period"),
                "to_period": metrics["cagr"].get("to_period"),
            },
            "cash_flow": {
                key: _metric_cell(metrics["cash_flow"].get(key))
                for key in ("fcf", "fcf_base", "fcf_conversion", "fcf_yield", "ebitda")
            },
            "balance_sheet": {
                key: _metric_cell(metrics["balance_sheet"].get(key))
                for key in (
                    "net_debt",
                    "net_debt_to_ebitda",
                    "interest_coverage",
                    "current_ratio",
                )
            },
            "per_share": {
                key: _metric_cell(metrics["per_share"].get(key))
                for key in (
                    "dilution_yoy",
                    "sbc_pct_revenue",
                    "sbc_pct_fcf",
                    "book_value_per_share",
                )
            },
            "returns": {"roe": _metric_cell((metrics.get("returns") or {}).get("roe"))},
            "quality_flags": metrics.get("quality_flags") or [],
        },
        "valuation": {
            "primary_multiple": valuation.get("primary_multiple"),
            "basis": valuation.get("basis"),
            "multiples": [
                {"key": key, "label": label, **_metric_cell(valuation.get(key))}
                for key, label in MULTIPLES
            ],
            "methods_used": valuation.get("methods_used"),
            "methods_skipped": valuation.get("methods_skipped"),
            "dcf": {
                "value_per_share": _metric_cell((valuation.get("dcf") or {}).get("value_per_share")),
                "upside_to_price": _metric_cell((valuation.get("dcf") or {}).get("upside_to_price")),
                "assumptions": {
                    "discount_rate": ((valuation.get("dcf") or {}).get("assumptions") or {})
                    .get("discount_rate", {})
                    .get("value"),
                    "terminal_growth": ((valuation.get("dcf") or {}).get("assumptions") or {})
                    .get("terminal_growth", {})
                    .get("value"),
                    "fcf_growth": ((valuation.get("dcf") or {}).get("assumptions") or {}).get(
                        "fcf_growth"
                    ),
                    "rates_are_nominal": True,
                },
            },
        },
        "peers": {
            "median": {
                key: _metric_cell((valuation.get("peer_table") or {}).get("median", {}).get(key))
                | {
                    "usable_peers": ((valuation.get("peer_table") or {}).get("median", {}).get(key) or {}).get("usable_peers"),
                    "peer_count": ((valuation.get("peer_table") or {}).get("median", {}).get(key) or {}).get("peer_count"),
                }
                for key in ("pe", "p_s", "ev_ebitda", "p_b")
            },
            "premium": {
                key: _metric_cell((valuation.get("vs_peers") or {}).get(f"{key}_premium"))
                for key in ("pe", "p_s", "ev_ebitda", "p_b")
            },
            "rows": [
                {
                    "ticker": row.get("ticker"),
                    "market_cap": (row.get("market_cap") or {}).get("value"),
                    "selection_reason": row.get("selection_reason"),
                    "multiples": {
                        key: (row.get("multiples") or {}).get(key, {}).get("value")
                        for key, _ in MULTIPLES
                    },
                }
                for row in (valuation.get("peer_table") or {}).get("peers", [])
            ],
        },
        "reverse_dcf": {
            "implied_fcf_cagr": _metric_cell(metrics["reverse_dcf"]["implied_fcf_cagr"]),
            "implied_fcf_cagr_smoothed_base": _metric_cell(
                metrics["reverse_dcf"].get("implied_fcf_cagr_smoothed_base")
            ),
            "assumptions": {
                "discount_rate": metrics["reverse_dcf"]["assumptions"]["discount_rate"]["value"],
                "terminal_growth": metrics["reverse_dcf"]["assumptions"]["terminal_growth"][
                    "value"
                ],
                "horizon_years": metrics["reverse_dcf"]["assumptions"]["horizon_years"],
            },
            "grid": [
                {
                    "discount_rate": cell["discount_rate"],
                    "terminal_growth": cell["terminal_growth"],
                    "implied_fcf_cagr": cell["implied_fcf_cagr"].get("value"),
                }
                for cell in metrics["reverse_dcf"]["sensitivity_grid"]
            ],
        },
        "notes": response.get("notes") or [],
        "filings": [
            {
                "accession": section.get("accession"),
                "item": section.get("item"),
                "url": (_sources(factsheet).get(section.get("source_id")) or {}).get("url"),
            }
            for section in (factsheet.get("filing_sections") or [])
        ],
        "generated_by": "calc.api.calculate_valuation over fixtures/real (no LLM, no network)",
    }


def main(tickers: list[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    done = []
    for ticker in tickers:
        try:
            payload = export(ticker)
        except Exception as exc:  # noqa: BLE001
            print(f"{ticker:6} FAIL {type(exc).__name__}: {exc}")
            continue
        (OUT / f"{ticker}.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
        done.append(
            {
                "ticker": ticker,
                "company_name": payload["company_name"],
                "as_of": payload["as_of"],
                "scope_level": payload["scope_level"],
                "price": payload["market"]["price"]["value"],
                "primary_multiple": payload["valuation"]["primary_multiple"],
            }
        )
        print(f"{ticker:6} OK   {payload['company_name']}")
    (OUT / "index.json").write_text(
        json.dumps(
            {
                "tickers": [row["ticker"] for row in done],
                "rows": done,
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "source": "fixtures/real recordings of SEC EDGAR filings; numbers computed by calc/",
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    return 0 if done else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or ["AAPL", "NVDA", "MSFT", "KO", "JPM"]))
