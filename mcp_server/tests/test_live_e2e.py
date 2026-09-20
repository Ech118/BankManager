"""Every served tool, for a real company, over a real stdio subprocess.

This is the only test in the repo that touches the network. It spawns
`python -m mcp_server.server` exactly as the orchestrator will in MODE=live,
speaks MCP over pipes, and calls all ten served tools for AAPL.

RUN IT WITH:
    BM_LIVE_TESTS=1 python -m pytest mcp_server/tests/test_live_e2e.py -q

Skipped otherwise, so a clone with no keys still runs the whole suite offline
and CI stays deterministic. `make check-live` is the other entry point.

WHAT IT IS FOR, AND WHAT IT IS NOT FOR
    It checks the WIRING: that the subprocess starts, that MODE reaches it, that
    every tool is advertised and answers, that responses validate against the
    contract models, and that point-in-time holds across the pipe. It is not a
    data-quality test - prices move and filings change, so it asserts shapes and
    invariants, never specific numbers.

    The one thing it does assert about magnitude is that Apple's market cap is
    somewhere between $100B and $20T, because a unit error there - thousands
    versus units, one share class versus all of them - is the failure that has
    actually happened twice in this partition.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import anyio
import pytest
from mcp import Client, StdioServerParameters

from schema.contracts.factsheet import Factsheet
from schema.contracts.tools import TOOL_RESPONSES

pytestmark = pytest.mark.live

ROOT = Path(__file__).resolve().parents[2]
TICKER = "AAPL"
AS_OF = "2026-09-19"

RUN_LIVE = os.environ.get("BM_LIVE_TESTS") == "1"

skip_unless_live = pytest.mark.skipif(
    not RUN_LIVE,
    reason="live test: set BM_LIVE_TESTS=1 (needs SEC_USER_AGENT and FINNHUB_API_KEY)",
)


def server_params() -> StdioServerParameters:
    """Spawn the server the way the orchestrator will."""
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server"],
        cwd=str(ROOT),
        env={**os.environ, "MODE": "live", "PYTHONPATH": str(ROOT)},
    )


def over_stdio(calls):
    """Open one subprocess, run `calls(client)` inside it, return the result.

    One subprocess for the whole test rather than one per tool: starting it
    costs about a second, and the point is that a single long-lived server
    answers every tool, which is how it will actually be used.
    """

    async def main():
        async with Client(server_params()) as client:
            return await calls(client)

    return anyio.run(main)


@pytest.fixture(scope="module")
def live_results():
    """Call every served tool once, in one session, and keep the answers."""

    async def calls(client):
        names = [t.name for t in (await client.list_tools()).tools]
        out = {"__tools__": names}

        arguments = {
            "get_company_profile": {"ticker": TICKER, "as_of": AS_OF},
            "get_market_snapshot": {"ticker": TICKER, "as_of": AS_OF},
            "get_financial_facts": {
                "ticker": TICKER,
                "metrics": ["revenue", "net_income", "total_debt"],
                "as_of": AS_OF,
            },
            "get_peer_companies": {"ticker": TICKER, "as_of": AS_OF, "limit": 6},
            "search_filings": {"ticker": TICKER, "as_of": AS_OF, "limit": 5},
            "search_filing": {
                "ticker": TICKER,
                "query": "supply chain concentration",
                "as_of": AS_OF,
            },
            "search_news": {"ticker": TICKER, "as_of": AS_OF, "limit": 5},
            "get_factsheet": {"ticker": TICKER, "as_of": AS_OF},
        }
        for name, args in arguments.items():
            result = await client.call_tool(name, args)
            out[name] = {
                "is_error": result.is_error,
                "content": result.structured_content,
                "text": result.content[0].text if result.content else "",
            }

        # These two need an id produced by an earlier call.
        facts = out["get_financial_facts"]["content"] or {}
        if facts.get("facts"):
            fact_id = facts["facts"][0]["fact_id"]
            result = await client.call_tool(
                "resolve_fact", {"fact_id": fact_id, "as_of": AS_OF}
            )
            out["resolve_fact"] = {
                "is_error": result.is_error,
                "content": result.structured_content,
                "requested_id": fact_id,
            }

        sections = out["search_filing"]["content"] or {}
        if sections.get("sections"):
            section_id = sections["sections"][0]["section_id"]
            result = await client.call_tool(
                "get_filing_section",
                {"section_id": section_id, "as_of": AS_OF, "max_chars": 4000},
            )
            out["get_filing_section"] = {
                "is_error": result.is_error,
                "content": result.structured_content,
                "requested_id": section_id,
            }
        return out

    return over_stdio(calls)


# --------------------------------------------------------------------------
# the subprocess, and the roster
# --------------------------------------------------------------------------
@skip_unless_live
def test_the_server_starts_over_stdio_and_advertises_its_tools(live_results):
    from mcp_server.server import IMPLEMENTED_TOOLS

    assert set(live_results["__tools__"]) == set(IMPLEMENTED_TOOLS)


@skip_unless_live
def test_every_tool_answered_without_an_error(live_results):
    failures = {
        name: payload.get("text")
        for name, payload in live_results.items()
        if name != "__tools__" and payload.get("is_error")
    }
    assert not failures, f"tools failed in live mode: {failures}"


@skip_unless_live
@pytest.mark.parametrize(
    "tool",
    [
        "get_company_profile",
        "get_market_snapshot",
        "get_financial_facts",
        "get_peer_companies",
        "search_filings",
        "search_filing",
        "search_news",
        "resolve_fact",
        "get_filing_section",
    ],
)
def test_each_response_validates_against_its_contract(live_results, tool):
    payload = live_results.get(tool)
    assert payload is not None, f"{tool} was never called"
    TOOL_RESPONSES[tool].model_validate(payload["content"])


# --------------------------------------------------------------------------
# what each tool actually returned
# --------------------------------------------------------------------------
@skip_unless_live
def test_the_profile_is_apple_with_a_sic_code(live_results):
    profile = live_results["get_company_profile"]["content"]["profile"]
    assert profile["cik"].lstrip("0") == "320193"
    assert profile["sic"]
    assert "apple" in profile["company_name"].lower()


@skip_unless_live
def test_the_market_cap_is_the_right_order_of_magnitude(live_results):
    """A unit error here - thousands vs units, one share class vs all of them -
    is the failure that has actually happened twice in this partition."""
    market = live_results["get_market_snapshot"]["content"]["snapshot"]
    cap = market["market_cap"]["value"]
    assert cap is not None, "no market cap in live mode"
    assert 1e11 < cap < 2e13, f"Apple's market cap came back as {cap}"


@skip_unless_live
def test_the_market_cap_is_price_times_shares(live_results):
    market = live_results["get_market_snapshot"]["content"]["snapshot"]
    price = market["price"]["value"]
    shares = market["shares_outstanding"]["value"]
    assert price and shares
    assert abs(market["market_cap"]["value"] - price * shares) / (price * shares) < 0.01


@skip_unless_live
def test_the_facts_are_real_and_cite_a_filing(live_results):
    facts = live_results["get_financial_facts"]["content"]["facts"]
    assert facts, "no facts in live mode"
    revenue = next(f for f in facts if f["metric"] == "revenue")
    assert revenue["value"] > 1e11
    assert revenue["accession_number"]
    assert revenue["filed_at"] <= AS_OF


@skip_unless_live
def test_peers_are_other_companies_with_reasons(live_results):
    peers = live_results["get_peer_companies"]["content"]["peers"]
    assert peers
    for peer in peers:
        assert peer["ticker"] != TICKER
        assert peer["selection_reason"]


@skip_unless_live
def test_the_extracted_section_is_a_real_item(live_results):
    payload = live_results["get_filing_section"]["content"]["section"]
    assert payload["text"].lower().lstrip().startswith("item 1")
    assert payload["char_end"] - payload["char_start"] == payload["char_count"]
    assert payload["char_count"] == len(payload["text"])


@skip_unless_live
def test_the_factsheet_is_complete_enough_to_audit(live_results):
    """The composition root hands exactly this object to audit.run_audit."""
    factsheet = Factsheet.model_validate(
        live_results["get_factsheet"]["content"]["factsheet"]
    )
    assert factsheet.ticker == TICKER
    assert len(factsheet.financials) >= 3
    assert factsheet.sp500_baseline.forward_pe.value
    assert factsheet.filing_sections
    assert factsheet.peers


# --------------------------------------------------------------------------
# point in time survives the pipe
# --------------------------------------------------------------------------
@skip_unless_live
def test_nothing_filed_after_as_of_crossed_the_wire(live_results):
    facts = live_results["get_financial_facts"]["content"]["facts"]
    assert all(not f["filed_at"] or f["filed_at"] <= AS_OF for f in facts)

    filings = live_results["search_filings"]["content"]["filings"]
    assert all(f["filed_at"] <= AS_OF for f in filings)

    news = live_results["search_news"]["content"]["news"]
    assert all(n["date"] <= AS_OF for n in news)


@skip_unless_live
def test_resolve_fact_round_trips_an_id_it_issued(live_results):
    payload = live_results["resolve_fact"]
    assert payload["content"]["fact"]["fact_id"] == payload["requested_id"]
    assert payload["content"]["is_future"] is False


# --------------------------------------------------------------------------
# failures still read like failures over a subprocess
# --------------------------------------------------------------------------
@skip_unless_live
def test_an_out_of_scope_ticker_fails_readably_over_stdio():
    """A protocol exception would abort the agent's turn; a readable error does
    not. This is the one property most easily lost across a transport."""

    async def calls(client):
        return await client.call_tool(
            "get_market_snapshot", {"ticker": "NOTAREALTICKER", "as_of": AS_OF}
        )

    result = over_stdio(calls)
    assert result.is_error
    assert "NOTAREALTICKER" in result.content[0].text


@skip_unless_live
def test_calculate_valuation_is_not_advertised_while_calc_is_missing(live_results):
    """Better absent than raising: an agent that plans around a tool which
    errors is worse off than one that knows the tool does not exist."""
    assert "calculate_valuation" not in live_results["__tools__"]
