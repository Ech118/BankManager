"""The S&P 500 baseline.

Offline by construction: `build` takes a quote rather than fetching one, so
nothing here needs a network or a key.
"""

from __future__ import annotations

import pytest

from data.ingest.market_client import Quote
from data.normalize import baseline
from schema.contracts.factsheet import SP500Baseline

AS_OF = "2026-09-19"
RETRIEVED = "2026-09-19T12:00:00Z"


def build(quote=None, as_of=AS_OF):
    return baseline.build(as_of=as_of, quote=quote, retrieved_at=RETRIEVED)


def spy(price=671.5, observed_at=1758300000, previous_close=668.2):
    return Quote("SPY", price, observed_at, previous_close=previous_close)


# --------------------------------------------------------------------------
# never unfilled
# --------------------------------------------------------------------------
def test_every_required_field_is_populated_with_a_quote():
    result = build(spy())
    for name in ("forward_pe", "earnings_yield", "risk_free_rate"):
        value = getattr(result.baseline, name)
        assert value.status.value == "ok", name
        assert value.value is not None, name


def test_every_required_field_is_populated_without_a_quote():
    """A provider outage costs the measured fields, never the assumptions."""
    result = build(quote=None)
    for name in ("forward_pe", "earnings_yield", "risk_free_rate"):
        assert getattr(result.baseline, name).status.value == "ok", name


def test_a_missing_quote_is_unavailable_plus_a_gap_not_a_zero():
    result = build(quote=None)
    price = result.baseline.model_dump()["spy_price"]
    assert price["value"] is None
    assert price["status"] == "unavailable"
    assert result.gaps and "SPY" in result.gaps[0]


def test_a_missing_quote_does_not_raise():
    assert build(quote=None).baseline.as_of == AS_OF


# --------------------------------------------------------------------------
# what is chosen vs what is measured
# --------------------------------------------------------------------------
def test_the_three_index_figures_are_typed_as_assumptions():
    """They render as a chosen input, not as something we measured."""
    result = build(spy())
    for name in ("forward_pe", "earnings_yield", "risk_free_rate"):
        assert getattr(result.baseline, name).type.value == "assumption", name


def test_the_spy_price_is_typed_as_a_fact():
    result = build(spy())
    assert result.baseline.model_dump()["spy_price"]["type"] == "fact"


def test_baseline_assumptions_are_mutually_consistent():
    """earnings_yield is 1/forward_pe. They are stored separately because P1
    does no arithmetic, which means nothing stops them drifting except this."""
    assert baseline.EARNINGS_YIELD == pytest.approx(1 / baseline.FORWARD_PE, rel=0.01)


def test_rates_are_fractions_not_percents():
    """0.0425 means 4.25%. The ValueObject validator catches >1.5, but 4.25
    would pass it while being a hundred times too large."""
    assert 0 < baseline.RISK_FREE_RATE < 0.25
    assert 0 < baseline.EARNINGS_YIELD < 0.25


def test_no_fabricated_index_level():
    """SPY tracks the index at about a tenth of its level. Multiplying by ten
    would produce a plausible-looking number that nobody published."""
    dumped = build(spy()).baseline.model_dump()
    assert "spy_price" in dumped
    assert not {k for k in dumped if "sp500_level" in k or "index_level" in k}


# --------------------------------------------------------------------------
# provenance
# --------------------------------------------------------------------------
def test_every_source_id_resolves_in_the_returned_sources():
    """The Factsheet validator rejects a citation that does not resolve, so the
    baseline has to hand back the registry entries for what it cited."""
    result = build(spy())
    cited = {
        v["source_id"]
        for v in result.baseline.model_dump().values()
        if isinstance(v, dict) and v.get("source_id")
    }
    assert cited
    assert cited <= set(result.sources)


def test_the_assumption_source_is_kind_config():
    result = build(spy())
    assert result.sources[baseline.CONFIG_SOURCE_ID].kind == "config"


def test_the_quote_source_is_kind_market():
    result = build(spy())
    market = [s for k, s in result.sources.items() if k.startswith("src:market")]
    assert [s.kind for s in market] == ["market"]


def test_changing_the_assumptions_version_changes_the_source_id():
    """Two runs with different baselines must not cite the same source."""
    assert baseline.ASSUMPTIONS_VERSION in baseline.CONFIG_SOURCE_ID


# --------------------------------------------------------------------------
# point in time
# --------------------------------------------------------------------------
def test_a_backtest_never_stamps_the_quote_after_its_cutoff():
    """A quote is always "now"; for a run dated in the past the honest instant
    is the end of the as_of day (ADR 0003)."""
    result = build(spy(observed_at=1758300000), as_of="2024-01-05")
    stamp = result.baseline.model_dump()["spy_price"]["source_id"]
    assert stamp.endswith("20240105T235959Z")


def test_the_baseline_as_of_is_the_run_as_of():
    assert build(spy(), as_of="2025-03-04").baseline.as_of == "2025-03-04"


def test_the_result_validates_as_the_contract_model():
    raw = build(spy()).baseline.model_dump(mode="json")
    assert SP500Baseline.model_validate(raw).forward_pe.value == baseline.FORWARD_PE
