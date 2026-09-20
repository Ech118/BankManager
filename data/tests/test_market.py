"""The market snapshot, against recorded provider responses.

Nothing here touches the network. `RecordedMarketClient` replays the
`finnhub.json` that `python -m data.record.market` captured per ticker, so the
degraded paths are exercised offline and deterministically.

Each ticker is here because it breaks a plausible implementation:

  AAPL   the easy case, and the one that proves the arithmetic.
  GOOGL  dei:EntityCommonStockSharesOutstanding is ABSENT - Alphabet tags it
         per share class, and companyfacts serves only consolidated facts.
  BRK-B  the tag is PRESENT and wrong: 941,481 Class A shares against a $903B
         public float. Finnhub's shareOutstanding repeats the same mistake.
  WDFC   a small cap, where a share count off by 1000x would still look sane.
  JPM    a bank: priced fine, but no total debt, so no enterprise value.
"""

from __future__ import annotations

import pytest

from data.ingest import market_client
from data.normalize import shares as shares_rules
from data.normalize import snapshot as snapshot_rules
from data.normalize import to_facts
from data.record.companyfacts import load
from data.record.market import RecordedMarketClient
from schema.contracts.market import MarketSnapshot

AS_OF = "2026-09-19"
RECORDED = ["AAPL", "BRK.B", "GOOGL", "NVDA", "WDFC", "KO", "JPM", "MSFT"]


@pytest.fixture(scope="module")
def client():
    return RecordedMarketClient(RECORDED)


@pytest.fixture(scope="module")
def facts_by_ticker():
    out = {}
    for ticker in ["AAPL", "GOOGL", "BRK-B", "WDFC", "KO", "NVDA", "JPM"]:
        companyfacts, _ = load(ticker)
        out[ticker] = (
            companyfacts,
            to_facts.normalize_companyfacts(
                ticker, companyfacts, as_of=AS_OF, cik=str(companyfacts.get("cik"))
            ),
        )
    return out


def build(client, facts_by_ticker, ticker, *, as_of=AS_OF, quote=..., profile=...):
    companyfacts, normalized = facts_by_ticker[ticker]
    return snapshot_rules.build(
        ticker,
        as_of=as_of,
        quote=client.quote(ticker) if quote is ... else quote,
        profile=client.profile(ticker) if profile is ... else profile,
        companyfacts=companyfacts,
        facts=normalized.facts,
        retrieved_at="2026-09-19T12:00:00Z",
    )


# --------------------------------------------------------------------------
# the happy path
# --------------------------------------------------------------------------
def test_snapshot_validates_and_bridges(client, facts_by_ticker):
    result = build(client, facts_by_ticker, "AAPL")
    snapshot = result.snapshot
    MarketSnapshot.model_validate(snapshot.model_dump(mode="json"))

    assert snapshot.price.value == pytest.approx(336.13)
    assert snapshot.market_cap.value == pytest.approx(
        snapshot.price.value * snapshot.shares_outstanding.value
    )
    assert snapshot.enterprise_value.value == pytest.approx(
        snapshot.market_cap.value + snapshot.total_debt.value - snapshot.cash.value
    )
    assert not result.gaps


def test_one_timestamp_for_every_field(client, facts_by_ticker):
    """The whole bundle is observed at one instant, by construction."""
    snapshot = build(client, facts_by_ticker, "AAPL").snapshot
    assert snapshot.as_of.endswith("Z")
    assert snapshot.as_of[:10] <= AS_OF
    assert snapshot.source_id.startswith("src:market:AAPL:")


def test_ev_inputs_cite_the_facts_they_came_from(client, facts_by_ticker):
    """cash and debt are the truth layer's, not the provider's."""
    _, normalized = facts_by_ticker["AAPL"]
    snapshot = build(client, facts_by_ticker, "AAPL").snapshot
    fact_ids = {f.fact_id for f in normalized.facts}
    assert snapshot.cash.derived_from[0] in fact_ids
    assert snapshot.total_debt.derived_from[0] in fact_ids


def test_backtest_never_claims_a_future_observation(client, facts_by_ticker):
    """A quote is always "now"; for a past as_of the honest stamp is that day."""
    snapshot = build(client, facts_by_ticker, "AAPL", as_of="2024-06-30").snapshot
    assert snapshot.as_of[:10] <= "2024-06-30"


# --------------------------------------------------------------------------
# share counts: the number that decides whether market cap is real
# --------------------------------------------------------------------------
def test_googl_falls_back_when_the_dei_tag_is_absent(client, facts_by_ticker):
    """Alphabet tags the cover-page count per class, so it is dimensioned and
    companyfacts drops it entirely."""
    companyfacts, _ = facts_by_ticker["GOOGL"]
    assert "EntityCommonStockSharesOutstanding" not in companyfacts["facts"].get("dei", {})

    snapshot = build(client, facts_by_ticker, "GOOGL").snapshot
    assert snapshot.shares_outstanding.xbrl_concept == "us-gaap:CommonStockSharesOutstanding"
    assert snapshot.shares_outstanding.value == pytest.approx(12_230_000_000)
    assert snapshot.market_cap.value == pytest.approx(4.27e12, rel=0.01)


def test_brk_b_rejects_the_class_a_only_count(client, facts_by_ticker):
    """941,481 Class A shares at a Class B price is a $480M Berkshire."""
    result = build(client, facts_by_ticker, "BRK-B")
    snapshot = result.snapshot

    assert snapshot.shares_outstanding.value is not None
    assert snapshot.shares_outstanding.xbrl_concept != "dei:EntityCommonStockSharesOutstanding"
    assert snapshot.market_cap.value == pytest.approx(9.8e11, rel=0.05)
    assert any("rejected" in gap for gap in result.gaps)


def test_brk_b_also_rejects_the_providers_share_count(client, facts_by_ticker):
    """Finnhub repeats the mistake: shareOutstanding is 1.44M, Class A again.
    Only its market cap covers both classes."""
    result = build(client, facts_by_ticker, "BRK-B")
    assert (
        result.snapshot.shares_outstanding.xbrl_concept
        == "finnhub:marketCapitalization/price"
    )
    rejected = " ".join(result.gaps)
    assert "finnhub:shareOutstanding" in rejected


def test_a_small_cap_share_count_is_not_rejected(client, facts_by_ticker):
    """The floor must not fire on a genuinely small company."""
    result = build(client, facts_by_ticker, "WDFC")
    snapshot = result.snapshot
    assert snapshot.shares_outstanding.value == pytest.approx(13_421_096)
    assert snapshot.market_cap.value == pytest.approx(2.54e9, rel=0.02)
    assert not [g for g in result.gaps if "rejected" in g]


def test_float_check_rejects_only_the_impossible():
    assert shares_rules.passes_float_check(1e9, 100.0, 5e10) is True
    # 941,481 Class A shares at $510 against a $903B float
    assert shares_rules.passes_float_check(941_481, 509.77, 902.7e9) is False
    # No price or no reported float: unverifiable is not the same as wrong.
    assert shares_rules.passes_float_check(1e9, None, 5e10) is True
    assert shares_rules.passes_float_check(1e9, 100.0, None) is True
    assert shares_rules.passes_float_check(0, 100.0, 5e10) is False


def test_filing_sourced_counts_are_tried_before_the_provider(client, facts_by_ticker):
    companyfacts, normalized = facts_by_ticker["AAPL"]
    options = shares_rules.candidates(
        companyfacts,
        as_of=AS_OF,
        provider_shares=1.0,
        provider_market_cap=2.0,
        price=336.13,
    )
    kinds = [o.source_kind.value for o in options]
    assert kinds.index("xbrl_reported") < kinds.index("market_api")


# --------------------------------------------------------------------------
# degrading, never crashing
# --------------------------------------------------------------------------
def test_provider_outage_yields_a_snapshot_with_price_unavailable(client, facts_by_ticker):
    result = build(client, facts_by_ticker, "AAPL", quote=None, profile=None)
    snapshot = result.snapshot

    MarketSnapshot.model_validate(snapshot.model_dump(mode="json"))
    assert snapshot.price.status.value == "unavailable"
    assert snapshot.price.value is None
    assert snapshot.market_cap.status.value == "unavailable"
    assert snapshot.enterprise_value.status.value == "unavailable"
    assert any("no price available" in gap for gap in result.gaps)


def test_cash_and_debt_survive_a_provider_outage(client, facts_by_ticker):
    """They come from filings, so a market outage must not touch them."""
    result = build(client, facts_by_ticker, "AAPL", quote=None, profile=None)
    assert result.snapshot.cash.value == pytest.approx(35_934_000_000)
    assert result.snapshot.total_debt.value == pytest.approx(98_657_000_000)


def test_a_bank_prices_fine_and_its_ev_is_left_to_scope_to_qualify(client, facts_by_ticker):
    """JPM resolves debt (500B) and cash (343B), so an EV arithmetically exists.

    It is economically meaningless - a bank's debt is raw material, not a claim
    to subtract - but that judgement belongs to check_scope's `partial` flag,
    not to the snapshot refusing to do arithmetic it was asked for.
    """
    result = build(client, facts_by_ticker, "JPM")
    assert result.snapshot.price.value == pytest.approx(349.67)
    assert result.snapshot.enterprise_value.status.value == "ok"

    from data.normalize import scope

    _, submissions = load("JPM")
    assert scope.classify("JPM", submissions, load("JPM")[0], AS_OF).level.value == "partial"


def test_an_insurer_with_no_debt_tag_has_no_enterprise_value(client, facts_by_ticker):
    """BRK-B tags no total debt at all, so the bridge cannot be built."""
    result = build(client, facts_by_ticker, "BRK-B")
    assert result.snapshot.total_debt.status.value == "unavailable"
    assert result.snapshot.enterprise_value.status.value == "unavailable"
    assert any("total_debt is not reported" in gap for gap in result.gaps)


def test_unknown_ticker_degrades_rather_than_raising(client, facts_by_ticker):
    assert client.quote("ZZZZ") is None
    assert client.profile("ZZZZ") is None
    assert client.peers("ZZZZ") == []
    assert client.news("ZZZZ", "2026-01-01", "2026-02-01") == []


def test_null_client_is_a_valid_market_client():
    null = market_client.NullMarketClient()
    assert isinstance(null, market_client.MarketClient)
    assert null.quote("AAPL") is None
    assert null.peers("AAPL") == []


def test_recorded_client_satisfies_the_protocol(client):
    assert isinstance(client, market_client.MarketClient)


# --------------------------------------------------------------------------
# the provider adapter
# --------------------------------------------------------------------------
def test_finnhub_spells_share_classes_with_a_dot():
    assert market_client.FinnhubClient.symbol("BRK-B") == "BRK.B"
    assert market_client.FinnhubClient.symbol("brk.b") == "BRK.B"
    assert market_client.FinnhubClient.symbol("AAPL") == "AAPL"


def test_finnhub_quantities_are_converted_from_millions():
    import httpx

    def handler(request):
        if "profile2" in request.url.path:
            return httpx.Response(
                200, json={"name": "X", "shareOutstanding": 1500.0, "marketCapitalization": 3000.0}
            )
        return httpx.Response(200, json={"c": 2.0, "t": 1789761600, "pc": 1.9})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    finnhub = market_client.FinnhubClient(api_key="test", http=http)
    profile = finnhub.profile("X")
    assert profile.shares_outstanding == pytest.approx(1.5e9)
    assert profile.market_cap == pytest.approx(3e9)


def test_a_failed_provider_call_returns_none_not_an_exception():
    import httpx

    def handler(request):
        return httpx.Response(429, json={"error": "rate limited"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    finnhub = market_client.FinnhubClient(api_key="test", http=http)
    assert finnhub.quote("AAPL") is None
    assert finnhub.profile("AAPL") is None
    assert finnhub.peers("AAPL") == []
    assert finnhub.news("AAPL", "2026-01-01", "2026-02-01") == []


def test_an_unknown_symbol_answers_200_with_zeroes():
    """Finnhub does not 404; it returns a quote of all zeroes."""
    import httpx

    def handler(request):
        return httpx.Response(200, json={"c": 0, "h": 0, "l": 0, "o": 0, "pc": 0, "t": 0})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    finnhub = market_client.FinnhubClient(api_key="test", http=http)
    assert finnhub.quote("ZZZZ") is None


def test_set_client_installs_and_resets():
    null = market_client.NullMarketClient()
    market_client.set_client(null)
    try:
        assert market_client.get_client() is null
    finally:
        market_client.set_client(None)
