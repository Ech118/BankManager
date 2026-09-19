"""Freezes the api.py signatures and the repository Protocols.

Changing a signature here is a CONTRACT-CHANGE PR: approval from all three
partitions plus a schema/CHANGELOG.md entry (CONTRIBUTING.md). Only the
coordinator edits this file, in the same commit that changes the signature.

Two rules are enforced structurally rather than by review:
  - every data read takes an `as_of` (ADR 0003);
  - no function that receives a factsheet ALSO takes an `as_of`, because the
    factsheet's own as_of is authoritative and a second one could disagree.
"""

import inspect

from audit import api as audit_api
from calc import api as calc_api
from data import api as data_api
from orchestrator import api as orch_api
from schema.contracts.interfaces import (
    FactRepository,
    FilingRepository,
    MarketRepository,
    McpClient,
)

EXPECTED = {
    # P1: data layer. Every read is point-in-time.
    (data_api, "check_scope"): ["ticker", "as_of=None"],
    (data_api, "build_factsheet"): ["ticker", "as_of=None"],
    (data_api, "search_filings"): ["ticker", "as_of=None", "forms=None", "limit=20"],
    (data_api, "get_filing_section"): ["section_id", "as_of=None"],
    (data_api, "get_section_text"): ["source_id", "as_of=None"],
    (data_api, "search_filing"): [
        "ticker", "query", "as_of=None", "forms=None", "items=None", "limit=10",
    ],
    (data_api, "get_financial_facts"): [
        "ticker", "metrics", "as_of=None", "period_type=None", "periods=None",
        "include_superseded=False",
    ],
    (data_api, "get_market_snapshot"): ["ticker", "as_of=None"],
    (data_api, "get_company_profile"): ["ticker", "as_of=None"],
    (data_api, "get_peer_companies"): ["ticker", "as_of=None", "limit=6"],
    (data_api, "search_news"): ["ticker", "as_of=None", "lookback_days=60", "limit=20"],
    (data_api, "resolve_fact"): ["fact_id", "as_of=None"],
    # P2: pure math. No as_of anywhere a factsheet is supplied.
    (calc_api, "compute_metrics"): ["factsheet"],
    (calc_api, "reverse_dcf"): ["factsheet", "metrics", "assumptions=None"],
    (calc_api, "calculate_valuation"): ["request"],
    (calc_api, "evaluate_scenarios"): ["scenarios", "factsheet", "metrics", "prior_shifts=None"],
    (calc_api, "derive_scores"): ["scenario_result"],
    (calc_api, "validate_consistency"): ["scenario_result", "verdict_card"],
    # P2: the verifier. Text and LLM access are injected, never imported.
    (audit_api, "run_audit"): ["state", "factsheet", "get_text", "verify_claim=None"],
    # P3: the pipeline. redact is the backtest anonymizer hook (error A).
    (orch_api, "run_analysis"): ["ticker", "as_of=None", "redact=None"],
}

DATA_READS = [
    name for (module, name) in EXPECTED if module is data_api and name != "check_scope"
]

FACTSHEET_CONSUMERS = [
    (module, name)
    for (module, name) in EXPECTED
    if "factsheet" in EXPECTED[(module, name)]
]


def _sig(fn):
    out = []
    for name, p in inspect.signature(fn).parameters.items():
        out.append(name if p.default is inspect.Parameter.empty else f"{name}={p.default!r}")
    return out


def test_api_signatures_are_frozen():
    for (module, name), expected in EXPECTED.items():
        assert _sig(getattr(module, name)) == expected, (
            f"{module.__name__}.{name} signature changed; this is a CONTRACT-CHANGE PR"
        )


def test_every_data_read_takes_as_of():
    """ADR 0003: there is no way to query the data layer without a cutoff."""
    for name in DATA_READS:
        params = inspect.signature(getattr(data_api, name)).parameters
        assert "as_of" in params, f"data.api.{name} must accept as_of"


def test_no_function_takes_both_a_factsheet_and_an_as_of():
    """Two sources of truth for the date is how a backtest silently leaks."""
    for module, name in FACTSHEET_CONSUMERS:
        params = inspect.signature(getattr(module, name)).parameters
        assert "as_of" not in params, (
            f"{module.__name__}.{name} takes a factsheet, so it must not also take an "
            "as_of; the factsheet's as_of is authoritative"
        )


def test_repository_protocols_are_runtime_checkable():
    """P1 implements these; P2 and P3 only ever see the Protocol."""
    for proto in (FactRepository, FilingRepository, MarketRepository, McpClient):
        assert getattr(proto, "_is_runtime_protocol", False), proto.__name__


def test_repository_protocol_methods_are_frozen():
    expected = {
        FactRepository: {"get_facts", "resolve_fact", "put_facts", "latest_period"},
        FilingRepository: {"search_filings", "get_section", "search_sections", "put_filing"},
        MarketRepository: {"get_snapshot", "get_profile", "get_peers", "search_news"},
        McpClient: {"call_tool", "list_tools", "close"},
    }
    for proto, methods in expected.items():
        actual = {
            m
            for m in dir(proto)
            if not m.startswith("_") and callable(getattr(proto, m, None))
        }
        assert actual == methods, f"{proto.__name__}: {actual ^ methods}"


def test_every_repository_read_takes_as_of():
    reads = {
        FactRepository: ["get_facts", "resolve_fact", "latest_period"],
        FilingRepository: ["search_filings", "get_section", "search_sections"],
        MarketRepository: ["get_snapshot", "get_profile", "get_peers", "search_news"],
    }
    for proto, methods in reads.items():
        for method in methods:
            params = inspect.signature(getattr(proto, method)).parameters
            assert "as_of" in params, f"{proto.__name__}.{method} must take as_of"
