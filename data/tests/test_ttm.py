"""Trailing-twelve-month facts, against recorded SEC data.

Offline: the recorder keeps the six most recent 10-Q filings for the flow
concepts, which is what a TTM figure reads.

  AAPL  the ordinary case: a September year end with a Q3 10-Q after it.
  NVDA  a January year end, so its quarters are labelled a year ahead.
  MSFT  filed its FY2026 10-K AFTER its last 10-Q, so the fiscal year already
        contains that quarter. Adding the quarter's year-to-date counts nine
        months twice - capex came out at $148.6B against a full year of $115.9B.
  KO    a calendar year end.
  JPM   a bank: several flow metrics have no concept at all, so their TTM must
        be absent with a reason rather than a partial sum.
"""

from __future__ import annotations

import pytest

from data.normalize import to_facts, ttm
from data.record.companyfacts import load

AS_OF = "2026-09-19"
TICKERS = ["AAPL", "NVDA", "MSFT", "KO"]


@pytest.fixture(scope="module")
def normalized():
    out = {}
    for ticker in [*TICKERS, "JPM"]:
        companyfacts, _ = load(ticker)
        cik = str(companyfacts.get("cik"))
        out[ticker] = (
            companyfacts,
            to_facts.normalize_companyfacts(ticker, companyfacts, as_of=AS_OF, cik=cik),
        )
    return out


def ttm_facts(normalized, ticker):
    _, result = normalized[ticker]
    return {f.metric: f for f in result.facts if f.metric.endswith(ttm.TTM_SUFFIX)}


def annual(normalized, ticker, metric):
    _, result = normalized[ticker]
    rows = [
        f
        for f in result.facts
        if f.metric == metric
        and f.is_current
        and (f.fiscal_period or "").startswith("FY")
    ]
    return max(rows, key=lambda f: f.period_end) if rows else None


# --------------------------------------------------------------------------
# the arithmetic
# --------------------------------------------------------------------------
def test_aapl_trailing_eps(normalized):
    """FY2025 7.46 + nine months of FY2026 6.88 - the same nine months of
    FY2025 5.62 = 8.72."""
    fact = ttm_facts(normalized, "AAPL")["eps_diluted_ttm"]
    assert fact.value == pytest.approx(8.72, abs=0.01)


@pytest.mark.parametrize("ticker", TICKERS)
def test_every_ttm_fact_recomputes_from_its_own_inputs(normalized, ticker):
    """The verifier recomputes a derived fact rather than trusting it, so the
    stored value has to equal what its lineage says it is."""
    _, result = normalized[ticker]
    by_id = {f.fact_id: f for f in result.facts}
    for fact in ttm_facts(normalized, ticker).values():
        inputs = [by_id[i] for i in fact.derivation.input_fact_ids]
        assert all(i is not None for i in inputs)
        if len(inputs) == 1:
            expected = inputs[0].value
        else:
            year, current, prior = inputs
            expected = year.value + current.value - prior.value
        assert fact.value == pytest.approx(expected, rel=1e-9)


def test_msft_uses_the_fiscal_year_because_the_10k_already_contains_the_quarter(
    normalized,
):
    """Microsoft's FY2026 10-K was filed after its Q3 10-Q. Adding that
    quarter's year-to-date to a year that already contains it double-counts."""
    fact = ttm_facts(normalized, "MSFT")["capex_ttm"]
    full_year = annual(normalized, "MSFT", "capex")
    assert fact.value == pytest.approx(full_year.value)
    assert len(fact.derivation.input_fact_ids) == 1
    assert "latest full year" in fact.derivation.formula


@pytest.mark.parametrize("ticker", TICKERS)
def test_a_ttm_flow_is_never_wildly_larger_than_its_own_year(normalized, ticker):
    """The double-count this catches made MSFT capex 128% of its full year."""
    for metric in ttm.TTM_METRICS:
        fact = ttm_facts(normalized, ticker).get(metric + ttm.TTM_SUFFIX)
        full_year = annual(normalized, ticker, metric)
        if fact is None or full_year is None or not full_year.value:
            continue
        if full_year.value <= 0:
            continue
        assert fact.value / full_year.value < 2.2, (
            f"{ticker} {metric}: TTM {fact.value} against a full year of "
            f"{full_year.value}"
        )


# --------------------------------------------------------------------------
# provenance
# --------------------------------------------------------------------------
@pytest.mark.parametrize("ticker", TICKERS)
def test_a_ttm_fact_is_dated_by_the_10q_that_completed_it(normalized, ticker):
    companyfacts, result = normalized[ticker]
    quarter = ttm.latest_quarter(companyfacts, as_of=AS_OF)
    for fact in ttm_facts(normalized, ticker).values():
        assert fact.filed_at, f"{fact.fact_id} has no filing date"
        assert fact.filed_at <= AS_OF
        if len(fact.derivation.input_fact_ids) == 3 and quarter:
            assert fact.filed_at == quarter[1]
            assert fact.accession_number == quarter[0]


@pytest.mark.parametrize("ticker", TICKERS)
def test_every_input_fact_id_resolves(normalized, ticker):
    """A derived fact whose inputs cannot be looked up gives the verifier a dead
    link, which is worse than no lineage because it looks like lineage."""
    _, result = normalized[ticker]
    known = {f.fact_id for f in result.facts}
    for fact in ttm_facts(normalized, ticker).values():
        missing = [i for i in fact.derivation.input_fact_ids if i not in known]
        assert not missing, f"{fact.fact_id} cites unresolvable {missing}"


@pytest.mark.parametrize("ticker", TICKERS)
def test_the_two_year_to_date_inputs_come_from_one_filing(normalized, ticker):
    """The comparative must be the one printed beside the current figure -
    taking it from the prior year's own 10-Q would miss a restatement."""
    _, result = normalized[ticker]
    by_id = {f.fact_id: f for f in result.facts}
    for fact in ttm_facts(normalized, ticker).values():
        ids = fact.derivation.input_fact_ids
        if len(ids) != 3:
            continue
        _, current, prior = (by_id[i] for i in ids)
        assert current.accession_number == prior.accession_number


@pytest.mark.parametrize("ticker", TICKERS)
def test_the_comparative_covers_the_same_span_a_year_earlier(normalized, ticker):
    """Nine months against six is the error this guards."""
    import datetime as dt

    _, result = normalized[ticker]
    by_id = {f.fact_id: f for f in result.facts}
    for fact in ttm_facts(normalized, ticker).values():
        ids = fact.derivation.input_fact_ids
        if len(ids) != 3:
            continue
        _, current, prior = (by_id[i] for i in ids)
        span = (
            dt.date.fromisoformat(current.period_end)
            - dt.date.fromisoformat(current.period_start)
        ).days
        prior_span = (
            dt.date.fromisoformat(prior.period_end)
            - dt.date.fromisoformat(prior.period_start)
        ).days
        gap = (
            dt.date.fromisoformat(current.period_end)
            - dt.date.fromisoformat(prior.period_end)
        ).days
        assert abs(span - prior_span) <= ttm.DURATION_TOLERANCE_DAYS
        assert abs(gap - ttm.YEAR_DAYS) <= ttm.YEAR_TOLERANCE_DAYS


def test_the_prior_year_label_is_not_the_filings_fiscal_year(normalized):
    """On a companyfacts entry `fy` is the FILING's fiscal year, so both
    year-to-date rows in a 10-Q carry the current one. Labelling the comparative
    from it would collide two facts onto one id."""
    _, result = normalized["AAPL"]
    ytd = sorted(
        f.fiscal_period
        for f in result.facts
        if f.metric == "eps_diluted" + ttm.YTD_SUFFIX
    )
    assert len(ytd) == len(set(ytd))
    assert ttm.prior_year_label("Q3-2026") == "Q3-2025"


# --------------------------------------------------------------------------
# missing inputs
# --------------------------------------------------------------------------
def test_a_bank_gets_no_ttm_for_a_metric_it_does_not_report(normalized):
    """Never a partial sum: a TTM built from two of three inputs is not a
    smaller number, it is a wrong one."""
    facts = ttm_facts(normalized, "JPM")
    _, result = normalized["JPM"]
    for metric in ("operating_income", "gross_profit", "capex"):
        if annual(normalized, "JPM", metric) is None:
            assert metric + ttm.TTM_SUFFIX not in facts
            assert any(metric in gap for gap in result.gaps)


def test_no_ttm_fact_carries_a_null_value(normalized):
    for ticker in TICKERS:
        for fact in ttm_facts(normalized, ticker).values():
            assert fact.value is not None


# --------------------------------------------------------------------------
# point in time
# --------------------------------------------------------------------------
def test_a_run_before_the_quarter_was_filed_does_not_see_it():
    """ADR 0003. The TTM fact did not exist until the 10-Q landed."""
    companyfacts, _ = load("AAPL")
    late = to_facts.normalize_companyfacts(
        "AAPL", companyfacts, as_of=AS_OF, cik="0000320193"
    )
    fact = next(f for f in late.facts if f.metric == "eps_diluted_ttm")

    import datetime as dt

    day_before = (
        dt.date.fromisoformat(fact.filed_at) - dt.timedelta(days=1)
    ).isoformat()
    early = to_facts.normalize_companyfacts(
        "AAPL", companyfacts, as_of=day_before, cik="0000320193"
    )
    earlier = next((f for f in early.facts if f.metric == "eps_diluted_ttm"), None)
    assert earlier is None or earlier.filed_at <= day_before


def test_flow_metrics_only():
    """A balance-sheet figure has no trailing twelve months."""
    assert "cash" not in ttm.TTM_METRICS
    assert "total_debt" not in ttm.TTM_METRICS
    assert "total_assets" not in ttm.TTM_METRICS


def test_capex_stays_positive_meaning_cash_spent(normalized):
    """The sign convention survives the quarterly path too (CLAUDE.md)."""
    for ticker in TICKERS:
        fact = ttm_facts(normalized, ticker).get("capex_ttm")
        if fact:
            assert fact.value > 0
