"""get_factsheet, exercised through a REAL MCP client.

The tool exists so the orchestrator can hand `audit.run_audit` a Factsheet
without importing `data/` (ADR 0007). Before it, P3 injected one from outside
the pipeline, which meant the object the auditor checked was not necessarily the
one the tools had answered from.

ACME's filings and what is visible when:

    0001234567-26-000090  10-Q  Q2-2026  filed 2026-08-05
    0001234567-26-000010  10-K  FY2025   filed 2026-02-20
    0001234567-25-000010  10-K  FY2024   filed 2025-02-21
    0001234567-24-000010  10-K  FY2023   filed 2024-02-22
"""

from mcp_server.tests.support import (
    BEFORE_FY2025_10K,
    LATEST,
    TICKER,
    call,
    error_text,
    list_tool_names,
    ok,
)
from schema.contracts.factsheet import Factsheet

BEFORE_ANY_FILING = "2020-01-01"
"""Earlier than ACME's oldest fixture filing: in scope, nothing to read."""


# --------------------------------------------------------------------------
# wiring
# --------------------------------------------------------------------------
def test_get_factsheet_is_advertised():
    assert "get_factsheet" in list_tool_names()


def test_the_response_validates_as_the_contract_model():
    payload = ok("get_factsheet", {"ticker": TICKER, "as_of": LATEST})
    factsheet = Factsheet.model_validate(payload["factsheet"])
    assert factsheet.ticker == TICKER


def test_as_of_is_required():
    assert call("get_factsheet", {"ticker": TICKER}).is_error


def test_an_out_of_scope_ticker_names_itself():
    message = error_text("get_factsheet", {"ticker": "BANKX", "as_of": LATEST})
    assert "BANKX" in message


# --------------------------------------------------------------------------
# what the auditor needs to be in it
# --------------------------------------------------------------------------
def test_it_carries_the_sections_that_audit_run_audit_reads():
    payload = ok("get_factsheet", {"ticker": TICKER, "as_of": LATEST})
    factsheet = Factsheet.model_validate(payload["factsheet"])
    assert factsheet.financials
    assert factsheet.market is not None
    assert factsheet.sp500_baseline is not None
    assert factsheet.sources


def test_every_source_id_cited_resolves_in_sources():
    """The Factsheet validator enforces this, so a regression here is a loud
    failure rather than a dead citation in a report."""
    payload = ok("get_factsheet", {"ticker": TICKER, "as_of": LATEST})
    factsheet = Factsheet.model_validate(payload["factsheet"])
    known = set(factsheet.sources)
    assert {s.source_id for s in factsheet.filing_sections} <= known
    assert {n.source_id for n in factsheet.news} <= known


# --------------------------------------------------------------------------
# point in time (ADR 0003)
# --------------------------------------------------------------------------
def test_the_returned_as_of_is_the_requested_one():
    payload = ok("get_factsheet", {"ticker": TICKER, "as_of": BEFORE_FY2025_10K})
    assert payload["as_of"] == BEFORE_FY2025_10K
    assert payload["factsheet"]["as_of"] == BEFORE_FY2025_10K


def test_nothing_filed_after_as_of_appears():
    payload = ok("get_factsheet", {"ticker": TICKER, "as_of": BEFORE_FY2025_10K})
    factsheet = Factsheet.model_validate(payload["factsheet"])
    assert all(p.filed_date <= BEFORE_FY2025_10K for p in factsheet.financials)
    assert all(s.filed_at <= BEFORE_FY2025_10K for s in factsheet.filing_sections)
    assert all(n.date <= BEFORE_FY2025_10K for n in factsheet.news)


def test_a_backtest_is_labelled_as_one():
    payload = ok("get_factsheet", {"ticker": TICKER, "as_of": BEFORE_FY2025_10K})
    assert payload["factsheet"]["mode"] == "backtest"


# --------------------------------------------------------------------------
# in scope but nothing to read is null, not an error
# --------------------------------------------------------------------------
def test_no_history_yet_is_a_null_factsheet_not_a_failure():
    """An agent must be able to tell "nothing filed yet" from "bad ticker"."""
    result = call("get_factsheet", {"ticker": TICKER, "as_of": BEFORE_ANY_FILING})
    assert not result.is_error
    assert result.structured_content["factsheet"] is None
