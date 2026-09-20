"""The two Step 3 filing tools, exercised through a REAL MCP client.

`search_filings` lets an agent see what exists before asking for contents, so it
fetches two sections rather than a whole 10-K. `get_filing_section` serves one
section verbatim.

The ACME fixture's filings, and what is visible when:

    0001234567-26-000090  10-Q  Q2-2026  filed 2026-08-05
    0001234567-26-000010  10-K  FY2025   filed 2026-02-20   <- has all 5 sections
    0001234567-25-000010  10-K  FY2024   filed 2025-02-21
    0001234567-24-000010  10-K  FY2023   filed 2024-02-22
"""

import anyio
import pytest
from mcp import Client

from mcp_server.server import build_server
from mcp_server.tests.support import (
    BEFORE_FY2025_10K,
    LATEST,
    TICKER,
    call,
    error_text,
    list_tool_names,
    ok,
)
from schema.contracts.tools import TOOL_REQUESTS

FY2025_10K = "0001234567-26-000010"

SECTION_LENGTHS = {
    "business": 914,
    "risk_factors": 751,
    "mdna": 1152,
    "debt_note": 937,
    "sbc_note": 1100,
}
"""Verbatim character counts, from the factsheet fixture's filing_sections."""

FILING_TOOLS = ["search_filings", "get_filing_section"]


def section_id(item: str) -> str:
    return f"sec:{FY2025_10K}:{item}"


def advertised(tool: str):
    async def go():
        async with Client(build_server()) as client:
            return {t.name: t for t in (await client.list_tools()).tools}

    return anyio.run(go)[tool]


# --------------------------------------------------------------------------
# Wiring
# --------------------------------------------------------------------------
@pytest.mark.parametrize("tool", FILING_TOOLS)
def test_tool_is_advertised(tool):
    assert tool in list_tool_names()


@pytest.mark.parametrize("tool", FILING_TOOLS)
def test_advertised_schema_matches_the_contract_model(tool):
    """The advertised inputSchema is generated from the contract model, so the
    two cannot drift apart. Asserting it keeps that guarantee honest."""
    schema = advertised(tool).input_schema
    assert set(schema["properties"]) == set(TOOL_REQUESTS[tool].model_fields)


@pytest.mark.parametrize("tool", FILING_TOOLS)
def test_as_of_is_required(tool):
    """Point-in-time is structural: no data tool may be callable without it."""
    assert "as_of" in advertised(tool).input_schema["required"]


# --------------------------------------------------------------------------
# search_filings
# --------------------------------------------------------------------------
def test_search_filings_returns_every_filing_newest_first():
    filings = ok("search_filings", {"ticker": TICKER, "as_of": LATEST})["filings"]

    assert [f["accession"] for f in filings] == [
        "0001234567-26-000090",
        "0001234567-26-000010",
        "0001234567-25-000010",
        "0001234567-24-000010",
    ]


def test_search_filings_hides_filings_not_yet_filed():
    """The core point-in-time rule: a run as of 2025-06-01 cannot see a filing
    submitted in 2026, no matter that it exists in the fixture today."""
    filings = ok("search_filings", {"ticker": TICKER, "as_of": BEFORE_FY2025_10K})["filings"]

    assert [f["accession"] for f in filings] == [
        "0001234567-25-000010",
        "0001234567-24-000010",
    ]
    assert all(f["filed_at"] <= BEFORE_FY2025_10K for f in filings)


def test_search_filings_filters_by_form():
    annual = ok("search_filings", {"ticker": TICKER, "as_of": LATEST, "forms": ["10-K"]})
    quarterly = ok("search_filings", {"ticker": TICKER, "as_of": LATEST, "forms": ["10-Q"]})

    assert {f["form"] for f in annual["filings"]} == {"10-K"}
    assert len(annual["filings"]) == 3
    assert [f["accession"] for f in quarterly["filings"]] == ["0001234567-26-000090"]


def test_search_filings_limit_sets_truncated():
    limited = ok("search_filings", {"ticker": TICKER, "as_of": LATEST, "limit": 2})

    assert len(limited["filings"]) == 2
    assert limited["truncated"] is True
    # Newest first, so a limit keeps the most recent filings.
    assert limited["filings"][0]["accession"] == "0001234567-26-000090"


def test_search_filings_not_truncated_when_limit_exceeds_the_result():
    full = ok("search_filings", {"ticker": TICKER, "as_of": LATEST, "limit": 20})
    assert full["truncated"] is False


def test_search_filings_out_of_scope_ticker_is_refused_with_a_reason():
    message = error_text("search_filings", {"ticker": "BANKX", "as_of": LATEST})
    assert "BANKX" in message
    assert "out of scope" in message.lower()


def test_search_filings_echoes_as_of():
    assert ok("search_filings", {"ticker": TICKER, "as_of": LATEST})["as_of"] == LATEST


# --------------------------------------------------------------------------
# get_filing_section
# --------------------------------------------------------------------------
@pytest.mark.parametrize("item", sorted(SECTION_LENGTHS))
def test_get_filing_section_returns_the_section_verbatim(item):
    section = ok("get_filing_section", {"section_id": section_id(item), "as_of": LATEST})[
        "section"
    ]

    assert section["section_id"] == section_id(item)
    assert section["source_id"].startswith("src:edgar:")
    assert section["item"] == item
    assert section["accession"] == FY2025_10K
    assert section["form"] == "10-K"
    # Verbatim: served at its full declared length, never summarised.
    assert len(section["text"]) == SECTION_LENGTHS[item]
    assert section["char_count"] == SECTION_LENGTHS[item]


def test_get_filing_section_text_is_the_real_fixture_prose():
    section = ok("get_filing_section", {"section_id": section_id("mdna"), "as_of": LATEST})[
        "section"
    ]
    assert "MANAGEMENT" in section["text"]
    assert "Revenue increased" in section["text"]


def test_unknown_section_id_is_an_error_not_an_empty_result():
    """An unknown id must not look like a section that exists but is empty."""
    message = error_text(
        "get_filing_section", {"section_id": "sec:nope:invented", "as_of": LATEST}
    )
    assert "sec:nope:invented" in message


def test_a_section_filed_after_as_of_is_an_error_not_an_empty_result():
    """docs/mcp-tools.md: silently returning nothing would look like the filing
    did not exist, rather than like it had not been filed yet."""
    message = error_text(
        "get_filing_section",
        {"section_id": section_id("mdna"), "as_of": BEFORE_FY2025_10K},
    )
    assert section_id("mdna") in message


def test_max_chars_truncates_and_keeps_the_offsets_consistent():
    """FilingSection's validator requires char_end - char_start == char_count ==
    len(text). A truncation that updated only `text` would fail to construct."""
    limit = 100
    payload = ok(
        "get_filing_section",
        {"section_id": section_id("mdna"), "as_of": LATEST, "max_chars": limit},
    )
    section = payload["section"]

    assert len(section["text"]) == limit
    assert section["char_count"] == limit
    assert section["char_end"] - section["char_start"] == limit
    assert payload["truncated"] is True


def test_truncated_text_is_a_verbatim_prefix():
    full = ok("get_filing_section", {"section_id": section_id("mdna"), "as_of": LATEST})
    cut = ok(
        "get_filing_section",
        {"section_id": section_id("mdna"), "as_of": LATEST, "max_chars": 100},
    )
    assert full["section"]["text"].startswith(cut["section"]["text"])


def test_max_chars_larger_than_the_section_does_not_truncate():
    payload = ok(
        "get_filing_section",
        {"section_id": section_id("business"), "as_of": LATEST, "max_chars": 100_000},
    )
    assert payload["truncated"] is False
    assert len(payload["section"]["text"]) == SECTION_LENGTHS["business"]


def test_omitting_as_of_is_an_error():
    assert call("get_filing_section", {"section_id": section_id("mdna")}).is_error
    assert call("search_filings", {"ticker": TICKER}).is_error
