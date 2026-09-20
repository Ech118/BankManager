"""The five Step 1 tools, exercised through a REAL MCP client.

Every test here goes over the MCP SDK's in-memory transport: a real client, a
real server, real tool dispatch and real argument validation. Nothing calls
`data.api` directly.

That is the point. If these tests shortcut to Python function calls, the wiring
P3 actually depends on would only ever be exercised in production
(docs/adr/0007-partition-boundaries.md).
"""

import anyio
import pytest
from mcp import Client

from mcp_server.server import IMPLEMENTED_TOOLS, build_server
from mcp_server.tests.support import (
    BEFORE_FY2025_10K,
    LATEST,
    TICKER,
    call,
    error_text,
    list_tool_names,
    ok,
)
from schema.contracts.tools import COMPUTE_TOOLS, TOOL_REQUESTS, TOOL_RESPONSES

BEFORE_RESTATEMENT = "2025-06-01"
"""After the FY2024 10-K (filed 2025-02-21), before the FY2025 10-K
(filed 2026-02-20) restated FY2024 operating cash flow from 690M to 700M."""

FY2024_AS_FILED = 690_000_000
FY2024_RESTATED = 700_000_000


# --------------------------------------------------------------------------
# Wiring
# --------------------------------------------------------------------------
def test_server_exposes_the_step_1_tools():
    assert sorted(list_tool_names()) == sorted(IMPLEMENTED_TOOLS)


def test_every_exposed_tool_is_a_contract_tool():
    """No tool may exist that the contracts do not describe."""
    for name in list_tool_names():
        assert name in TOOL_REQUESTS, f"{name} is not in schema.contracts.tools"


@pytest.mark.parametrize("name", sorted(IMPLEMENTED_TOOLS))
def test_advertised_schema_matches_the_contract_model(name):
    """The schema a client sees must be the model that validates the call.

    This is what stops a tool signature drifting away from the contract without
    anyone noticing until an agent sends the wrong arguments.
    """

    async def go():
        async with Client(build_server()) as client:
            return {t.name: t for t in (await client.list_tools()).tools}[name]

    tool = anyio.run(go)
    advertised = set(tool.input_schema.get("properties", {}))
    expected = set(TOOL_REQUESTS[name].model_fields)
    assert advertised == expected, f"{name}: advertised {advertised}, contract {expected}"


DATA_TOOLS = sorted(set(IMPLEMENTED_TOOLS) - COMPUTE_TOOLS)
"""Everything served except the compute tool.

`calculate_valuation` takes no `as_of` by design: the factsheet it works from
already carries the authoritative one, and a second date could silently
disagree with the first (amendment 2). Excluding it here rather than weakening
the assertion keeps "every DATA tool requires as_of" a real check - and
tests/contracts/test_models.py asserts the other half, that a compute tool does
not take one."""


@pytest.mark.parametrize("name", DATA_TOOLS)
def test_every_data_tool_requires_as_of(name):
    """ADR 0003: there is no way to query the data layer without a cutoff."""

    async def go():
        async with Client(build_server()) as client:
            return {t.name: t for t in (await client.list_tools()).tools}[name]

    tool = anyio.run(go)
    assert "as_of" in tool.input_schema.get("required", []), f"{name} must require as_of"


@pytest.mark.parametrize("name", DATA_TOOLS)
def test_omitting_as_of_is_an_error(name):
    result = call(name, {"ticker": TICKER})
    assert result.is_error, f"{name} accepted a call with no as_of"


def test_unknown_tool_is_an_error():
    assert call("get_something_invented", {"as_of": LATEST}).is_error


def test_unknown_argument_is_rejected():
    """Contract requests set extra='forbid', so a typo fails loudly."""
    result = call(
        "get_company_profile", {"ticker": TICKER, "as_of": LATEST, "tickr": "TYPO"}
    )
    assert result.is_error


# --------------------------------------------------------------------------
# get_financial_facts
# --------------------------------------------------------------------------
def test_get_financial_facts_returns_contract_valid_facts():
    out = ok(
        "get_financial_facts",
        {"ticker": TICKER, "metrics": ["revenue"], "as_of": LATEST},
    )
    parsed = TOOL_RESPONSES["get_financial_facts"].model_validate(out)
    assert parsed.facts, "expected at least one revenue fact"
    assert all(f.metric == "revenue" for f in parsed.facts)
    assert all(f.company_id == TICKER for f in parsed.facts)


def test_get_financial_facts_is_newest_first():
    out = ok(
        "get_financial_facts",
        {"ticker": TICKER, "metrics": ["revenue"], "as_of": LATEST},
    )
    ends = [f["period_end"] for f in out["facts"]]
    assert ends == sorted(ends, reverse=True)


def test_get_financial_facts_honours_the_periods_limit():
    out = ok(
        "get_financial_facts",
        {"ticker": TICKER, "metrics": ["revenue"], "as_of": LATEST, "periods": 2},
    )
    assert len(out["facts"]) == 2
    assert out["truncated"] is True


def test_get_financial_facts_excludes_facts_filed_after_as_of():
    out = ok(
        "get_financial_facts",
        {
            "ticker": TICKER,
            "metrics": ["revenue"],
            "as_of": BEFORE_RESTATEMENT,
            "include_superseded": True,
        },
    )
    assert out["facts"], "expected the FY2024 and FY2023 revenue facts"
    for fact in out["facts"]:
        assert fact["filed_at"] <= BEFORE_RESTATEMENT
    periods = {f["fiscal_period"] for f in out["facts"]}
    assert "FY2025" not in periods, "the FY2025 10-K was filed after the cutoff"


def test_unknown_metric_returns_no_rows_rather_than_an_error():
    """A gap is reported as absence, never as a crash or a zero."""
    out = ok(
        "get_financial_facts",
        {"ticker": TICKER, "metrics": ["gross_margin_percent"], "as_of": LATEST},
    )
    assert out["facts"] == []


# --------------------------------------------------------------------------
# The restatement. This is the behaviour the whole backtest rests on.
# --------------------------------------------------------------------------
def _fy2024_ocf(as_of: str, include_superseded: bool = False) -> list[dict]:
    out = ok(
        "get_financial_facts",
        {
            "ticker": TICKER,
            "metrics": ["op_cash_flow"],
            "as_of": as_of,
            "include_superseded": include_superseded,
        },
    )
    return [f for f in out["facts"] if f["fiscal_period"] == "FY2024"]


def test_before_the_restatement_the_as_filed_value_is_returned():
    """On 2025-06-01 the only FY2024 figure that existed was 690M."""
    facts = _fy2024_ocf(BEFORE_RESTATEMENT)
    assert len(facts) == 1
    assert facts[0]["value"] == FY2024_AS_FILED
    assert facts[0]["filed_at"] == "2025-02-21"


def test_after_the_restatement_the_corrected_value_is_returned():
    """Once the FY2025 10-K landed on 2026-02-20, FY2024 became 700M."""
    facts = _fy2024_ocf(LATEST)
    assert len(facts) == 1
    assert facts[0]["value"] == FY2024_RESTATED
    assert facts[0]["superseded_by"] is None


def test_the_restated_value_never_leaks_into_the_past():
    """The single check that keeps a backtest honest (error A)."""
    out = ok(
        "get_financial_facts",
        {
            "ticker": TICKER,
            "metrics": ["op_cash_flow"],
            "as_of": BEFORE_RESTATEMENT,
            "include_superseded": True,
        },
    )
    assert FY2024_RESTATED not in [f["value"] for f in out["facts"]]


def test_superseded_values_are_hidden_by_default_today():
    facts = _fy2024_ocf(LATEST, include_superseded=False)
    assert [f["value"] for f in facts] == [FY2024_RESTATED]


def test_include_superseded_shows_the_full_restatement_history():
    facts = _fy2024_ocf(LATEST, include_superseded=True)
    values = sorted(f["value"] for f in facts)
    assert values == [FY2024_AS_FILED, FY2024_RESTATED]
    old = next(f for f in facts if f["value"] == FY2024_AS_FILED)
    assert old["superseded_by"] == "fact:ACME:op_cash_flow:FY2024"


# --------------------------------------------------------------------------
# resolve_fact
# --------------------------------------------------------------------------
def test_resolve_fact_returns_the_fact():
    out = ok(
        "resolve_fact",
        {"fact_id": "fact:ACME:revenue:FY2025", "as_of": LATEST},
    )
    parsed = TOOL_RESPONSES["resolve_fact"].model_validate(out)
    assert parsed.fact is not None
    assert parsed.fact.value == 5_000_000_000
    assert parsed.is_superseded is False and parsed.is_future is False


def test_resolve_fact_flags_a_superseded_fact():
    """The verifier must be able to tell 'restated' from 'does not exist'."""
    out = ok(
        "resolve_fact",
        {"fact_id": "fact:ACME:op_cash_flow:FY2024:as-filed", "as_of": LATEST},
    )
    assert out["fact"] is not None
    assert out["is_superseded"] is True


def test_resolve_fact_flags_a_future_fact():
    """Cited from a run dated before the fact was filed -> IssueType.FUTURE_FACT."""
    out = ok(
        "resolve_fact",
        {"fact_id": "fact:ACME:revenue:FY2025", "as_of": BEFORE_RESTATEMENT},
    )
    assert out["fact"] is not None, "the fact exists; it is just not visible yet"
    assert out["is_future"] is True


def test_resolve_fact_returns_null_for_an_unknown_id():
    out = ok("resolve_fact", {"fact_id": "fact:ACME:nope:FY2025", "as_of": LATEST})
    assert out["fact"] is None
    assert out["is_superseded"] is False and out["is_future"] is False


def test_resolve_fact_resolves_a_derived_fact_with_its_lineage():
    out = ok("resolve_fact", {"fact_id": "fact:ACME:fcf:FY2025", "as_of": LATEST})
    fact = out["fact"]
    assert fact["source_kind"] == "derived"
    assert fact["derivation"]["formula"] == "op_cash_flow - capex"
    assert len(fact["derivation"]["input_fact_ids"]) == 2


# --------------------------------------------------------------------------
# get_market_snapshot
# --------------------------------------------------------------------------
def test_get_market_snapshot_returns_one_timestamped_snapshot():
    out = ok("get_market_snapshot", {"ticker": TICKER, "as_of": LATEST})
    parsed = TOOL_RESPONSES["get_market_snapshot"].model_validate(out)
    assert parsed.snapshot is not None
    snap = parsed.snapshot
    assert snap.price.value == 50.0
    assert snap.shares_outstanding.value == 395_000_000
    assert snap.market_cap.value == 19_750_000_000


def test_market_cap_is_consistent_with_price_and_shares():
    """A units bug here is worth catching at the boundary, not downstream."""
    snap = ok("get_market_snapshot", {"ticker": TICKER, "as_of": LATEST})["snapshot"]
    assert snap["market_cap"]["value"] == pytest.approx(
        snap["price"]["value"] * snap["shares_outstanding"]["value"]
    )


def test_market_snapshot_is_unavailable_before_it_was_observed():
    out = ok("get_market_snapshot", {"ticker": TICKER, "as_of": BEFORE_RESTATEMENT})
    assert out["snapshot"] is None, "a snapshot must not be visible before its as_of"


# --------------------------------------------------------------------------
# get_company_profile
# --------------------------------------------------------------------------
def test_get_company_profile():
    out = ok("get_company_profile", {"ticker": TICKER, "as_of": LATEST})
    parsed = TOOL_RESPONSES["get_company_profile"].model_validate(out)
    assert parsed.profile is not None
    assert parsed.profile.ticker == TICKER
    assert parsed.profile.sic == "3823"
    assert parsed.profile.fiscal_year_end == "12-31"


def test_unknown_ticker_is_refused_with_a_reason():
    """Out of scope must be a clear refusal, not an empty success."""
    result = call("get_company_profile", {"ticker": "NOPE", "as_of": LATEST})
    assert result.is_error
    assert "NOPE" in (result.content[0].text if result.content else "")


# --------------------------------------------------------------------------
# get_peer_companies
# --------------------------------------------------------------------------
def test_get_peer_companies():
    out = ok("get_peer_companies", {"ticker": TICKER, "as_of": LATEST})
    parsed = TOOL_RESPONSES["get_peer_companies"].model_validate(out)
    assert len(parsed.peers) == 4
    assert {p.ticker for p in parsed.peers} == {"PRAA", "PRBB", "PRCC", "PRDD"}
    assert all(p.selection_reason for p in parsed.peers), "each peer must justify itself"


def test_get_peer_companies_honours_limit():
    out = ok("get_peer_companies", {"ticker": TICKER, "as_of": LATEST, "limit": 2})
    assert len(out["peers"]) == 2
    assert out["truncated"] is True


# --------------------------------------------------------------------------
# The out-of-scope ticker still behaves
# --------------------------------------------------------------------------
def test_out_of_scope_ticker_is_refused_on_every_tool():
    """BANKX exercises the rejection path; it must never return data."""
    for tool, args in (
        ("search_filings", {}),
        ("get_financial_facts", {"metrics": ["revenue"]}),
        ("get_market_snapshot", {}),
        ("get_company_profile", {}),
        ("get_peer_companies", {}),
    ):
        result = call(tool, {"ticker": "BANKX", "as_of": LATEST, **args})
        assert result.is_error, f"{tool} did not refuse BANKX"


# --------------------------------------------------------------------------
# search_news: untrusted, bounded above as well as below
# --------------------------------------------------------------------------
def test_search_news_is_advertised():
    assert "search_news" in list_tool_names()


def test_search_news_returns_contract_items():
    payload = ok("search_news", {"ticker": TICKER, "as_of": LATEST})
    parsed = TOOL_RESPONSES["search_news"].model_validate(payload)
    for entry in parsed.news:
        assert entry.url.startswith(("http://", "https://"))
        assert entry.source_id


def test_search_news_never_returns_anything_after_as_of():
    payload = ok("search_news", {"ticker": TICKER, "as_of": BEFORE_FY2025_10K})
    assert all(n["date"] <= BEFORE_FY2025_10K for n in payload["news"])


def test_search_news_requires_as_of():
    assert call("search_news", {"ticker": TICKER}).is_error


def test_search_news_rejects_an_out_of_scope_ticker():
    assert "BANKX" in error_text("search_news", {"ticker": "BANKX", "as_of": LATEST})


def test_search_news_empty_is_not_an_error():
    """A provider outage must reach the agent as no news plus a gap, never as a
    failed call."""
    result = call("search_news", {"ticker": TICKER, "as_of": "2000-01-01"})
    assert not result.is_error
    assert result.structured_content["news"] == []


# --------------------------------------------------------------------------
# calculate_valuation: the one sanctioned cross-partition import
# --------------------------------------------------------------------------
def test_calculate_valuation_is_advertised():
    assert "calculate_valuation" in list_tool_names()


def test_calculate_valuation_takes_no_as_of():
    """A function given a factsheet must not take a second, possibly
    conflicting date (amendment 2)."""
    schema = TOOL_REQUESTS["calculate_valuation"].model_json_schema()
    assert "as_of" not in schema.get("properties", {})


def test_calculate_valuation_returns_a_contract_response():
    payload = ok(
        "calculate_valuation",
        {"ticker": TICKER, "methods": ["pe", "ev_revenue", "reverse_dcf"]},
    )
    TOOL_RESPONSES["calculate_valuation"].model_validate(payload)


def test_calculate_valuation_always_returns_a_sensitivity_grid():
    """Never a single point value (error D)."""
    payload = ok("calculate_valuation", {"ticker": TICKER, "methods": ["reverse_dcf"]})
    assert payload.get("reverse_dcf")
    assert payload["reverse_dcf"].get("sensitivity_grid")


def test_an_unknown_method_is_skipped_with_a_reason_not_raised():
    """One bad method name in an LLM's request must not lose the other six."""
    payload = ok(
        "calculate_valuation",
        {"ticker": TICKER, "methods": ["pe", "not_a_real_method"]},
    )
    skipped = payload["metrics"]["valuation"]["methods_skipped"]
    assert "not_a_real_method" in skipped
    assert skipped["not_a_real_method"]


def test_calculate_valuation_rejects_an_out_of_scope_ticker():
    assert "BANKX" in error_text(
        "calculate_valuation", {"ticker": "BANKX", "methods": ["pe"]}
    )


def test_the_wrapper_holds_no_arithmetic():
    """ADR 0007: arithmetic in this file is a defect. Checked mechanically
    because a reviewer will not notice a single `/` added later."""
    import ast
    import inspect

    from mcp_server.tools import calculate_valuation

    tree = ast.parse(inspect.getsource(calculate_valuation))
    operators = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Add | ast.Sub | ast.Mult | ast.Div | ast.Pow)
    ]
    assert not operators, "valuation arithmetic belongs in calc/, not in the wrapper"
