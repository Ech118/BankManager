"""`calculate_valuation`: the MCP-exposed entry point, assembled here.

`calc.api.calculate_valuation` is a one-line delegate to this module, and
`mcp_server/tools/calculate_valuation.py` (P1) is a thin wrapper over that - the
one sanctioned cross-partition import in the repo (ADR 0007). No formula lives on
either side of that boundary except here.

## How the factsheet gets in

`calc/` is pure: it cannot turn a ticker into a factsheet, because that would
mean a network or a database. So the caller supplies one:

```python
calc.api.calculate_valuation({**request, "factsheet": factsheet})
```

`CalculateValuationRequest` itself forbids extra fields, so P1 validates the
LLM's request first and adds `factsheet` to the dict afterwards. In mock mode a
request naming ACME with no factsheet falls back to `fixtures/mock/factsheet.json`
so the contract suite can call the tool with nothing but a ticker.

## Methods

`pe | ev_ebitda | ev_revenue | p_fcf | p_s | p_b | peer_median | dcf |
reverse_dcf | historical`, plus `all`. A method whose inputs are unavailable is
**skipped with its reason recorded** in `notes` and in `methods_skipped`, never
silently dropped and never guessed.
"""

from __future__ import annotations

import json
from pathlib import Path

from calc.facts import Ledger, is_partial_scope
from calc.metrics.compute import compute_metrics
from calc.valuation.dcf import simple_dcf
from calc.valuation.historical import historical_block
from calc.valuation.peers import PEER_FIELDS, compare, peer_table

MOCK_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "mock"

MULTIPLE_METHODS = ("pe", "forward_pe", "ev_ebitda", "ev_revenue", "p_fcf", "p_s", "p_b")
ALL_METHODS = (*MULTIPLE_METHODS, "peer_median", "dcf", "reverse_dcf", "historical")

ALIASES = {
    "all": ALL_METHODS,
    "multiples": MULTIPLE_METHODS,
    "peers": ("peer_median",),
    "peer_comparison": ("peer_median",),
    "p_e": ("pe",),
    "p_s": ("p_s",),
    "ps": ("p_s",),
    "pb": ("p_b",),
    "price_to_book": ("p_b",),
    "ev_sales": ("ev_revenue",),
    "historical_multiples": ("historical",),
}


def _expand(methods: list[str] | None) -> list[str]:
    if not methods:
        return list(ALL_METHODS)
    out: list[str] = []
    for method in methods:
        for name in ALIASES.get(method, (method,)):
            if name not in out:
                out.append(name)
    return out


def _mock_factsheet(ticker: str) -> dict:
    factsheet = json.loads((MOCK_DIR / "factsheet.json").read_text(encoding="utf-8"))
    if ticker and ticker != factsheet["ticker"]:
        raise ValueError(
            f"calculate_valuation: no factsheet supplied for {ticker}. calc/ is pure and "
            "cannot fetch one; pass request['factsheet'] (mcp_server/tools/"
            "calculate_valuation.py does this). Only ACME has a mock fallback."
        )
    return factsheet


def calculate_valuation(request: dict) -> dict:
    """CalculateValuationRequest -> CalculateValuationResponse."""
    factsheet = request.get("factsheet") or _mock_factsheet(request.get("ticker", ""))
    assumptions = request.get("assumptions") or None
    requested = _expand(request.get("methods"))

    metrics = compute_metrics(factsheet, assumptions)
    ledger = Ledger(factsheet)
    ledger.adopt(metrics["derived_facts"] + metrics["input_facts"])
    partial = is_partial_scope(factsheet)
    valuation = metrics["valuation"]

    notes: list[str] = []
    used: list[str] = []
    skipped: dict[str, str] = {}

    for method in requested:
        if method in MULTIPLE_METHODS:
            vo = valuation.get(method)
            if vo is None:
                skipped[method] = f"unknown method '{method}'"
            elif vo.get("value") is None:
                skipped[method] = vo.get("unavailable_reason") or "inputs unavailable"
            else:
                used.append(method)
            continue

        if method == "peer_median":
            table = peer_table(ledger)
            valuation["peer_table"] = table
            premiums = compare(ledger, valuation, table)
            valuation["vs_peers"] = {**valuation.get("vs_peers", {}), **premiums}
            backed = [f for f in PEER_FIELDS if table["median"][f].get("value") is not None]
            if backed:
                used.append(method)
            else:
                skipped[method] = table["median"]["pe"].get("unavailable_reason") or "no peer data"
            continue

        if method == "dcf":
            block = simple_dcf(ledger, metrics, assumptions)
            valuation["dcf"] = block
            if block["value_per_share"].get("value") is None:
                skipped[method] = block["value_per_share"].get("unavailable_reason") or "no FCF"
            else:
                used.append(method)
            continue

        if method == "reverse_dcf":
            if metrics["reverse_dcf"]["implied_fcf_cagr"].get("value") is None:
                skipped[method] = (
                    metrics["reverse_dcf"]["implied_fcf_cagr"].get("unavailable_reason")
                    or "no positive FCF"
                )
            else:
                used.append(method)
            continue

        if method == "historical":
            valuation["historical"] = historical_block(valuation)
            skipped[method] = valuation["historical"]["reason"]
            continue

        skipped[method] = f"unknown method '{method}'"

    # The extra blocks were built on a second ledger, so fold their derived facts
    # into the run's list, keyed by fact_id: one fact per id, first one wins.
    by_id = {f["fact_id"]: f for f in metrics["derived_facts"]}
    for fact in ledger.derived_facts:
        by_id.setdefault(fact["fact_id"], fact)
    metrics["derived_facts"] = list(by_id.values())
    minted = {f["fact_id"]: f for f in metrics["input_facts"]}
    for fact in ledger.input_facts:
        minted.setdefault(fact["fact_id"], fact)
    metrics["input_facts"] = list(minted.values())

    valuation["methods_used"] = used
    valuation["methods_skipped"] = skipped
    for method, why in skipped.items():
        notes.append(f"{method}: skipped - {why}")
    if partial:
        notes.append(
            f"{factsheet['ticker']} is partial scope (bank, insurer, broker or REIT): "
            "P/B is the primary multiple and the enterprise-value methods are not applicable"
        )
    notes.extend(metrics.get("notes") or [])

    return {
        "metrics": metrics,
        "reverse_dcf": metrics["reverse_dcf"],
        "notes": notes,
        "as_of": factsheet["as_of"],
        "truncated": False,
    }
