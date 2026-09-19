"""Rule 3: live-mode check. Skipped unless run as:

    MODE=live BM_TEST_TICKER=<ticker> make check-live

Proves the real data layer produces a contract-valid factsheet for a real
company, and that point-in-time queries actually exclude later filings.
"""

import os

import pytest
from conftest import ORIGINAL_MODE
from helpers import validation_errors

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        ORIGINAL_MODE != "live" or not os.environ.get("BM_TEST_TICKER"),
        reason="set MODE=live and BM_TEST_TICKER=<ticker> to run",
    ),
]


def test_live_factsheet_validates():
    from data import api

    ticker = os.environ["BM_TEST_TICKER"]
    assert api.check_scope(ticker)["in_scope"]
    errs = validation_errors(api.build_factsheet(ticker), "factsheet.json")
    assert not errs, "\n".join(errs)


def test_live_point_in_time_excludes_later_filings():
    """The backtest is worthless if as_of leaks (error A, ADR 0003)."""
    from data import api

    ticker = os.environ["BM_TEST_TICKER"]
    cutoff = os.environ.get("BM_TEST_AS_OF", "2023-06-30")
    fs = api.build_factsheet(ticker, as_of=cutoff)
    assert fs["as_of"] == cutoff
    assert all(p["filed_date"] <= cutoff for p in fs["financials"])
    assert all(s["filed_at"] <= cutoff for s in fs["filing_sections"])


def test_live_facts_carry_provenance():
    from data import api

    ticker = os.environ["BM_TEST_TICKER"]
    facts = api.get_financial_facts(ticker, ["revenue"], as_of="2024-12-31")
    assert facts, "expected at least one revenue fact"
    for fact in facts:
        assert fact["accession_number"] and fact["filed_at"] and fact["retrieved_at"]
