"""MCP client: real protocol, contract validation, point-in-time, transports.

Runs against tests/e2e/support/fake_mcp.py, a P3-owned test double that speaks
genuine MCP. Swap in the real server object when P1 ships it.
"""

import sys

import pytest

from orchestrator.mcp_client import (
    InMemoryMcpClient,
    McpServerUnavailable,
    McpToolError,
    StdioMcpClient,
    ToolArgumentError,
    build_client,
)
from schema.contracts.tools import TOOL_REQUESTS
from tests.e2e.support.fake_mcp import build_fake_server


@pytest.fixture()
def mcp():
    client = InMemoryMcpClient(build_fake_server())
    yield client
    client.close()


def test_mock_mode_speaks_real_mcp_not_a_shortcut(mcp):
    """Tool discovery and calls go through the SDK session, so the tool schema is the server's own."""
    tools = mcp.list_tools()
    assert set(tools) <= set(TOOL_REQUESTS) and "get_financial_facts" in tools
    assert mcp._sync._session.__class__.__name__ in (
        "ClientSession",
        "Client",
    )  # a real MCP client session
    out = mcp.call_tool(
        "get_financial_facts", {"ticker": "ACME", "metrics": ["revenue"], "as_of": "2026-09-19"}
    )
    assert out["facts"] and out["as_of"] == "2026-09-19"


def test_invalid_tool_arguments_fail_in_p3_with_a_clear_message(mcp):
    server_calls = []
    orig = mcp._sync.request
    mcp._sync.request = lambda fn, *a, **k: (server_calls.append(1), orig(fn, *a, **k))[1]
    with pytest.raises(ToolArgumentError, match="get_financial_facts"):
        mcp.call_tool(
            "get_financial_facts", {"ticker": "acme lower!", "metrics": [], "as_of": "yesterday"}
        )
    with pytest.raises(ToolArgumentError):  # as_of is required on data tools
        mcp.call_tool("get_financial_facts", {"ticker": "ACME", "metrics": ["revenue"]})
    with pytest.raises(ToolArgumentError):  # extra="forbid" on requests
        mcp.call_tool(
            "get_financial_facts",
            {"ticker": "ACME", "metrics": ["revenue"], "as_of": "2026-09-19", "x": 1},
        )
    assert server_calls == []  # never reached the server


def test_unknown_tool_is_a_keyerror_listing_the_surface(mcp):
    with pytest.raises(KeyError, match="get_financial_facts"):
        mcp.call_tool("delete_everything", {})


def test_point_in_time_nothing_filed_after_as_of(mcp):
    latest = mcp.call_tool(
        "get_financial_facts", {"ticker": "ACME", "metrics": ["revenue"], "as_of": "2026-09-19"}
    )
    early = mcp.call_tool(
        "get_financial_facts", {"ticker": "ACME", "metrics": ["revenue"], "as_of": "2025-03-01"}
    )
    assert {"FY2025", "Q2-2026"} <= {f["fiscal_period"] for f in latest["facts"]}
    assert all(f["filed_at"] <= "2025-03-01" for f in early["facts"])
    assert "FY2025" not in {f["fiscal_period"] for f in early["facts"]}


def test_restated_facts_are_excluded_unless_asked_for(mcp):
    args = {"ticker": "ACME", "metrics": ["op_cash_flow"], "as_of": "2026-09-19"}
    default = mcp.call_tool("get_financial_facts", args)["facts"]
    with_old = mcp.call_tool("get_financial_facts", {**args, "include_superseded": True})["facts"]
    assert all(f["superseded_by"] is None for f in default)
    assert len(with_old) > len(default)


def test_server_errors_become_mcp_tool_errors_with_the_reason(mcp):
    with pytest.raises(McpToolError):  # section filed after as_of => an error, not empty
        mcp.call_tool(
            "get_filing_section",
            {"section_id": "sec:0001234567-26-000010:mdna", "as_of": "2025-01-01"},
        )
    with pytest.raises(McpToolError):
        mcp.call_tool("get_filing_section", {"section_id": "sec:nope:mdna", "as_of": "2026-09-19"})


def test_section_text_is_verbatim_and_max_chars_truncates(mcp):
    full = mcp.call_tool(
        "get_filing_section", {"section_id": "sec:0001234567-26-000010:mdna", "as_of": "2026-09-19"}
    )
    cut = mcp.call_tool(
        "get_filing_section",
        {"section_id": "sec:0001234567-26-000010:mdna", "as_of": "2026-09-19", "max_chars": 50},
    )
    assert "Gross margin improved to 40.0%" in full["section"]["text"] and not full["truncated"]
    assert len(cut["section"]["text"]) == 50 and cut["truncated"]


def test_close_is_idempotent_and_blocks_further_calls():
    client = InMemoryMcpClient(build_fake_server())
    client.close()
    client.close()
    with pytest.raises(McpServerUnavailable):
        client.call_tool(
            "get_financial_facts", {"ticker": "ACME", "metrics": ["revenue"], "as_of": "2026-09-19"}
        )


def test_in_memory_client_needs_an_injected_server():
    with pytest.raises(McpServerUnavailable, match="composition root"):
        InMemoryMcpClient(None)
    with pytest.raises(McpServerUnavailable):
        build_client("mock")


def test_stdio_transport_works_against_a_spawned_server():
    """Live mode's transport, exercised for real: spawns the test-double as a subprocess."""
    client = StdioMcpClient([sys.executable, "-m", "tests.e2e.support.fake_mcp"])
    try:
        assert "get_financial_facts" in client.list_tools()
        out = client.call_tool("get_company_profile", {"ticker": "ACME", "as_of": "2026-09-19"})
        assert out["profile"]["ticker"] == "ACME"
    finally:
        client.close()
