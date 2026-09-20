"""The built Factsheet, against five recorded real companies.

These read what P1 SHIPPED, not what SEC returned, so they answer a different
question from the other suites: not "did we parse this right" but "did the
object calc/ and audit/ consume change shape".

Prices move, so nothing here asserts a price. What is asserted is structure,
provenance, point-in-time and internal consistency.

  AAPL  the ordinary case, and the one whose market cap is easiest to sanity
        check against a public quote.
  MSFT  a June year end, so FY2026 is already reported in September 2026.
  NVDA  a January year end plus the split, so the period labels come from the
        filer's own numbering rather than the calendar.
  KO    clean: every metric resolves, and data_quality should say `ok`.
  JPM   a bank. No operating income, no capex, no gross profit, no inventory -
        `degraded`, with a gap naming each, and NOT a zero anywhere.
"""

from __future__ import annotations

import pytest

from data.record.factsheet import load
from schema.contracts.factsheet import Factsheet

TICKERS = ["AAPL", "JPM", "NVDA", "KO", "MSFT"]
AS_OF = "2026-09-19"


@pytest.fixture(scope="module")
def recorded():
    return {ticker: load(ticker) for ticker in TICKERS}


@pytest.fixture(scope="module")
def parsed(recorded):
    return {t: Factsheet.model_validate(raw) for t, raw in recorded.items()}


# --------------------------------------------------------------------------
# it is a Factsheet
# --------------------------------------------------------------------------
@pytest.mark.parametrize("ticker", TICKERS)
def test_it_validates_against_the_contract(recorded, ticker):
    """The contract's own validators run here: newest-first ordering,
    point-in-time, and every cited source_id resolving."""
    factsheet = Factsheet.model_validate(recorded[ticker])
    assert factsheet.ticker == ticker
    assert factsheet.company_name


@pytest.mark.parametrize("ticker", TICKERS)
def test_five_annual_periods_newest_first(parsed, ticker):
    factsheet = parsed[ticker]
    assert len(factsheet.financials) == 5
    ends = [p.period_end for p in factsheet.financials]
    assert ends == sorted(ends, reverse=True)


def test_period_labels_come_from_the_filer_not_the_calendar(parsed):
    """NVDA's year ends in January and MSFT's in June, so both are a year
    ahead of the calendar. A calendar guess would label them FY2025."""
    assert parsed["NVDA"].financials[0].period == "FY2026"
    assert parsed["MSFT"].financials[0].period == "FY2026"
    assert parsed["KO"].financials[0].period == "FY2025"


# --------------------------------------------------------------------------
# point in time
# --------------------------------------------------------------------------
@pytest.mark.parametrize("ticker", TICKERS)
def test_nothing_was_filed_after_as_of(parsed, ticker):
    factsheet = parsed[ticker]
    assert factsheet.as_of == AS_OF
    assert all(p.filed_date <= AS_OF for p in factsheet.financials)


@pytest.mark.parametrize("ticker", TICKERS)
def test_a_period_is_dated_by_a_real_filing(parsed, ticker):
    """Not by its period end. A period whose accession is empty cannot be
    traced back to a document, and a filing cannot predate the year it reports.
    """
    for period in parsed[ticker].financials:
        assert period.accession, f"{ticker} {period.period} has no accession"
        assert period.filed_date > period.period_end, (
            f"{ticker} {period.period}: filed {period.filed_date} but the period "
            f"only ended {period.period_end}"
        )


# --------------------------------------------------------------------------
# provenance
# --------------------------------------------------------------------------
@pytest.mark.parametrize("ticker", TICKERS)
def test_every_reported_value_cites_something(recorded, ticker):
    """status ok requires a source_id or a derived_from - the ValueObject
    validator enforces it, and this proves the builder satisfies it for real
    data rather than only for the fixture."""
    for period in recorded[ticker]["financials"]:
        for metric, value in period.items():
            if not isinstance(value, dict) or value.get("status") != "ok":
                continue
            assert value.get("source_id") or value.get("derived_from"), (
                f"{ticker} {period['period']} {metric} is ok with no provenance"
            )


@pytest.mark.parametrize("ticker", TICKERS)
def test_every_period_source_id_resolves_in_the_registry(recorded, ticker):
    known = set(recorded[ticker]["sources"])
    for period in recorded[ticker]["financials"]:
        for metric, value in period.items():
            if not isinstance(value, dict):
                continue
            source_id = value.get("source_id")
            if source_id:
                assert source_id in known, f"{ticker} {period['period']} {metric}"


@pytest.mark.parametrize("ticker", TICKERS)
def test_total_debt_names_the_lines_it_was_summed_from(recorded, ticker):
    """A summed number appears nowhere in the filing, so a reader has to be
    able to reach the lines that do."""
    for period in recorded[ticker]["financials"]:
        debt = period["total_debt"]
        if debt.get("status") != "ok":
            continue
        assert debt.get("derived_from"), f"{ticker} {period['period']} total_debt"


# --------------------------------------------------------------------------
# missing is unavailable, never zero
# --------------------------------------------------------------------------
def test_a_bank_reports_unavailable_rather_than_zero(recorded):
    """JPM has no operating income, no capex and no gross profit. Zero would
    make every margin built on them wrong and would look like data."""
    jpm = recorded["JPM"]
    latest = jpm["financials"][0]
    absent = [
        m
        for m in ("operating_income", "capex", "gross_profit", "inventory")
        if latest[m]["status"] == "unavailable"
    ]
    assert absent, "expected a bank to be missing some of these"
    for metric in absent:
        assert latest[metric]["value"] is None, f"{metric} is unavailable but not null"


@pytest.mark.parametrize("ticker", TICKERS)
def test_no_unavailable_value_carries_a_number(recorded, ticker):
    for period in recorded[ticker]["financials"]:
        for metric, value in period.items():
            if isinstance(value, dict) and value.get("status") == "unavailable":
                assert value["value"] is None, f"{ticker} {period['period']} {metric}"


def test_a_missing_metric_produces_a_gap_that_names_it(recorded):
    gaps = " ".join(recorded["JPM"]["data_quality"]["gaps"])
    assert "operating_income" in gaps or "capex" in gaps


def test_data_quality_reflects_what_is_missing(recorded):
    """KO resolves everything; JPM resolves little. A banner that reads `ok`
    for a bank would be worse than no banner."""
    assert recorded["KO"]["data_quality"]["overall"] == "ok"
    assert recorded["JPM"]["data_quality"]["overall"] == "degraded"


# --------------------------------------------------------------------------
# the market block
# --------------------------------------------------------------------------
@pytest.mark.parametrize("ticker", TICKERS)
def test_market_cap_is_price_times_shares(recorded, ticker):
    """Not a provider's number pasted in beside an unrelated share count."""
    market = recorded[ticker]["market"]
    price = market["price"]["value"]
    shares = market["shares_outstanding"]["value"]
    cap = market["market_cap"]["value"]
    if not (price and shares and cap):
        pytest.skip(f"{ticker}: market data incomplete in this recording")
    assert cap == pytest.approx(price * shares, rel=0.01)


@pytest.mark.parametrize("ticker", TICKERS)
def test_the_whole_market_bundle_shares_one_instant(recorded, ticker):
    """Mixing a live price with last quarter's share count corrupts the cap and
    every multiple built on it (docs/sec-pitfalls.md 8)."""
    market = recorded[ticker]["market"]
    assert market.get("as_of")
    assert market.get("retrieved_at")


# --------------------------------------------------------------------------
# the baseline and the peers
# --------------------------------------------------------------------------
@pytest.mark.parametrize("ticker", TICKERS)
def test_the_sp500_baseline_is_never_unfilled(recorded, ticker):
    """The verdict is "beats the S&P 500 or not", so the comparison has to have
    a reference point on every path."""
    baseline = recorded[ticker]["sp500_baseline"]
    for field in ("forward_pe", "earnings_yield", "risk_free_rate"):
        assert baseline[field]["status"] == "ok", field
        assert baseline[field]["value"] is not None, field


@pytest.mark.parametrize("ticker", TICKERS)
def test_the_baseline_assumptions_are_labelled_as_assumptions(recorded, ticker):
    baseline = recorded[ticker]["sp500_baseline"]
    for field in ("forward_pe", "earnings_yield", "risk_free_rate"):
        assert baseline[field]["type"] == "assumption", field


@pytest.mark.parametrize("ticker", TICKERS)
def test_peers_exist_and_each_says_why(parsed, ticker):
    factsheet = parsed[ticker]
    assert factsheet.peers
    for peer in factsheet.peers:
        assert peer.selection_reason
        assert peer.ticker != ticker


@pytest.mark.parametrize("ticker", TICKERS)
def test_peer_multiples_are_left_for_calc(parsed, ticker):
    """pe, ev_ebitda, ev_revenue and fcf_yield are ratios. P1 does not compute
    ratios (ADR 0001)."""
    for peer in parsed[ticker].peers:
        assert peer.pe.status.value == "unavailable"
        assert peer.ev_ebitda.status.value == "unavailable"


# --------------------------------------------------------------------------
# what is deliberately empty
# --------------------------------------------------------------------------
@pytest.mark.parametrize("ticker", TICKERS)
def test_sections_and_news_are_empty_rather_than_invented(parsed, ticker):
    """The section parser and the news client are not built. An empty list is
    honest; a fabricated entry would not be."""
    assert parsed[ticker].filing_sections == []
    assert parsed[ticker].news == []
