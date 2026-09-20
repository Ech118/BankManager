"""XBRL normalization, against recorded SEC responses.

Nothing here touches the network. Every test reads a companyfacts payload that
`python -m data.record.companyfacts` pulled once into fixtures/real/, so a
failure means our code changed - not that SEC was slow today.

The fixtures are real companies and the expected values below were read off
their filings. Each one is here because it broke a plausible implementation:

  AAPL   debt is LongTermDebt + CommercialPaper, and LongTermDebt already
         contains the current maturities that LongTermDebtCurrent restates.
  NVDA   capex changes tag mid-history; a 10-for-1 split retroactively
         restated FY2024's share count; the fiscal year ends in January.
  KO     stopped tagging LongTermDebt after FY2023.
  WDFC   reports a genuine combined total, and its year ends in August.
  GOOGL  tags no GrossProfit and no InventoryNet.
  JPM    no operating income, no capex, and a SIC that makes it partial.
  O      a REIT whose debt is NotesPayable.
  TSM    a 20-F filer with no us-gaap taxonomy at all.
  XOM    a ticker whose SEC-mapped CIK is a holding company with no history.
"""

from __future__ import annotations

import pytest

from data.ingest.ticker_overrides import override_for
from data.normalize import (
    concept_map,
    derived,
    dimensions,
    periods,
    restatements,
    scope,
    splits,
    to_facts,
)
from data.record.companyfacts import load
from schema.contracts.facts import FinancialFact

AS_OF = "2026-09-19"

OPERATING_COMPANIES = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "KO", "WDFC"]


@pytest.fixture(scope="module")
def recorded():
    """ticker -> (companyfacts, submissions), read once for the whole module."""
    tickers = [*OPERATING_COMPANIES, "JPM", "O", "TSM", "XOM", "XOM-HOLDCO", "BRK-B"]
    return {t: load(t) for t in tickers}


def normalize(recorded, ticker, **kwargs):
    companyfacts, _ = recorded[ticker]
    return to_facts.normalize_companyfacts(
        ticker.split("-HOLDCO")[0],
        companyfacts,
        as_of=kwargs.pop("as_of", AS_OF),
        cik=str(companyfacts.get("cik")),
        **kwargs,
    )


def value_of(result, metric, period):
    facts = [
        f
        for f in result.facts
        if f.metric == metric and f.fiscal_period == period and f.is_current
    ]
    return facts[0] if facts else None


# --------------------------------------------------------------------------
# the chains
# --------------------------------------------------------------------------
@pytest.mark.parametrize("ticker", OPERATING_COMPANIES)
def test_core_metrics_resolve_for_every_operating_company(recorded, ticker):
    """The metrics a valuation cannot proceed without, for all seven filers."""
    result = normalize(recorded, ticker)
    latest = result.periods[0].label
    for metric in ("revenue", "net_income", "op_cash_flow", "capex", "cash", "total_debt"):
        fact = value_of(result, metric, latest)
        assert fact is not None, f"{ticker} {latest}: {metric} did not resolve"
        assert fact.value is not None and fact.value != 0


@pytest.mark.parametrize("ticker", OPERATING_COMPANIES)
def test_five_fiscal_years(recorded, ticker):
    result = normalize(recorded, ticker)
    assert len(result.periods) == 5
    labels = [p.label for p in result.periods]
    assert labels == sorted(labels, reverse=True), "periods must be newest first"


def test_every_fact_validates_against_the_contract(recorded):
    """Round-trip through the model: provenance rules are not bypassed."""
    result = normalize(recorded, "AAPL")
    for fact in result.facts:
        FinancialFact.model_validate(fact.model_dump(mode="json"))


def test_winning_concept_is_recorded_on_the_fact(recorded):
    result = normalize(recorded, "NVDA")
    revenue = value_of(result, "revenue", "FY2026")
    assert revenue.xbrl_concept == "Revenues"
    assert revenue.source_location == "us-gaap:Revenues"
    assert revenue.source_url.startswith("https://www.sec.gov/Archives/edgar/data/1045810/")


def test_nvda_capex_switches_tag_between_periods(recorded):
    """A chain resolved once per company would lose the older years."""
    result = normalize(recorded, "NVDA", years=20)
    by_period = {
        f.fiscal_period: f.xbrl_concept
        for f in result.facts
        if f.metric == "capex" and f.is_current
    }
    assert by_period["FY2026"] == "PaymentsToAcquireProductiveAssets"
    oldest = min(by_period)
    assert by_period[oldest] == "PaymentsToAcquirePropertyPlantAndEquipment"


def test_aapl_revenue_switches_tag_between_periods(recorded):
    result = normalize(recorded, "AAPL", years=12)
    by_period = {
        f.fiscal_period: f.xbrl_concept
        for f in result.facts
        if f.metric == "revenue" and f.is_current
    }
    assert by_period["FY2025"] == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert by_period["FY2015"] == "SalesRevenueNet"


# --------------------------------------------------------------------------
# fiscal years are not calendar years
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("ticker", "label", "period_end"),
    [
        ("NVDA", "FY2026", "2026-01-25"),  # January year end
        ("MSFT", "FY2026", "2026-06-30"),  # June
        ("WDFC", "FY2025", "2025-08-31"),  # August
        ("AAPL", "FY2025", "2025-09-27"),  # September, 52/53-week
        ("KO", "FY2025", "2025-12-31"),  # calendar
    ],
)
def test_fiscal_year_label_comes_from_the_filer(recorded, ticker, label, period_end):
    """NVDA's year ending January 2026 is FY2026 because NVDA says so."""
    result = normalize(recorded, ticker)
    assert result.periods[0].label == label
    assert result.periods[0].period_end == period_end


def test_labels_are_consecutive_and_unique(recorded):
    result = normalize(recorded, "AAPL", years=10)
    years = [p.fiscal_year for p in result.periods]
    assert years == sorted(set(years), reverse=True)
    assert years[0] - years[-1] == len(years) - 1


# --------------------------------------------------------------------------
# total debt
# --------------------------------------------------------------------------
def test_aapl_debt_sums_long_term_and_commercial_paper(recorded):
    """90,678M + 7,979M. LongTermDebtCurrent is already inside LongTermDebt."""
    result = normalize(recorded, "AAPL")
    total = value_of(result, "total_debt", "FY2025")
    assert total.value == pytest.approx(98_657_000_000)
    assert total.xbrl_concept == "LongTermDebt+CommercialPaper"


def test_nvda_debt_does_not_double_count_current_maturities(recorded):
    """NVDA tags DebtCurrent and LongTermDebtCurrent as the same 999M, and
    LongTermDebt (8,468M) already contains it. Summing gives 9,467M."""
    result = normalize(recorded, "NVDA")
    total = value_of(result, "total_debt", "FY2026")
    assert total.value == pytest.approx(8_468_000_000)
    assert total.xbrl_concept == "LongTermDebt"


def test_ko_debt_survives_the_tag_change_after_fy2023(recorded):
    """KO stopped tagging LongTermDebt; only the capital-lease tags remain."""
    result = normalize(recorded, "KO")
    total = value_of(result, "total_debt", "FY2025")
    assert total.value == pytest.approx(45_492_000_000)
    assert "CommercialPaper" in total.xbrl_concept
    assert "OtherShortTermBorrowings" in total.xbrl_concept


def test_wdfc_uses_the_reported_combined_total(recorded):
    """A filer that reports a real total needs no sum, and no derivation."""
    result = normalize(recorded, "WDFC")
    total = value_of(result, "total_debt", "FY2025")
    assert total.value == pytest.approx(86_995_000)
    assert total.xbrl_concept == "DebtLongtermAndShorttermCombinedAmount"
    assert total.source_kind.value == "xbrl_reported"
    assert total.derivation is None


def test_reit_debt_falls_through_to_notes_payable(recorded):
    result = normalize(recorded, "O")
    total = value_of(result, "total_debt", "FY2025")
    assert total is not None
    assert "NotesPayable" in total.xbrl_concept


def test_summed_debt_is_derived_with_clickable_components(recorded):
    """The total appears in no filing, so its parts must be reachable facts."""
    result = normalize(recorded, "AAPL")
    total = value_of(result, "total_debt", "FY2025")

    assert total.source_kind.value == "derived"
    assert total.derivation is not None
    assert total.derivation.computed_by == to_facts.COMPUTED_BY
    assert total.derivation.computed_by != "calc"

    by_id = {f.fact_id: f for f in result.facts}
    parts = [by_id[fact_id] for fact_id in total.derivation.input_fact_ids]
    assert len(parts) == 2
    assert sum(p.value for p in parts) == pytest.approx(total.value)
    for part in parts:
        assert part.source_kind.value == "xbrl_reported"
        assert part.accession_number and part.source_url
        assert part.is_current, "a component is current, not superseded by its siblings"


def test_debt_components_do_not_supersede_each_other(recorded):
    """Without a discriminator, CommercialPaper looks like a restatement of
    LongTermDebt: same metric, same period, different value."""
    result = normalize(recorded, "KO")
    components = [
        f
        for f in result.facts
        if f.metric == to_facts.DEBT_COMPONENT_METRIC and f.fiscal_period == "FY2025"
    ]
    assert {f.xbrl_concept for f in components} == {
        "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
        "CommercialPaper",
        "OtherShortTermBorrowings",
    }
    assert all(f.is_current for f in components)


def test_derived_debt_carries_filed_at(recorded):
    """P3 compares filed_at to as_of; a null one crashed their client."""
    result = normalize(recorded, "AAPL")
    total = value_of(result, "total_debt", "FY2025")
    assert total.filed_at and total.accession_number


# --------------------------------------------------------------------------
# restatements and point-in-time
# --------------------------------------------------------------------------
def test_nvda_split_restates_fy2024_shares(recorded):
    """The 10-for-1 split of June 2024 restated FY2024's diluted share count
    from 2,494M to 24,940M. Both rows are kept; the older one is linked."""
    result = normalize(recorded, "NVDA")
    current = value_of(result, "shares_diluted", "FY2024")
    assert current.value == pytest.approx(24_940_000_000)

    superseded = [
        f
        for f in result.facts
        if f.metric == "shares_diluted" and f.fiscal_period == "FY2024" and not f.is_current
    ]
    assert len(superseded) == 1
    assert superseded[0].value == pytest.approx(2_494_000_000)
    assert superseded[0].superseded_by == current.fact_id
    assert superseded[0].filed_at < current.filed_at


def test_a_run_before_the_split_sees_the_pre_split_count(recorded):
    """ADR 0003: a run dated before the restatement must not see it."""
    result = normalize(recorded, "NVDA", as_of="2024-03-01")
    current = value_of(result, "shares_diluted", "FY2024")
    assert current.value == pytest.approx(2_494_000_000)
    assert current.is_current, "the as-filed value is current for a run that predates the fix"


def test_nothing_filed_after_as_of_is_visible(recorded):
    result = normalize(recorded, "AAPL", as_of="2024-01-01")
    assert all(f.filed_at <= "2024-01-01" for f in result.facts if f.filed_at)
    assert result.periods[0].label == "FY2023"


def test_as_known_on_reproduces_an_earlier_view(recorded):
    result = normalize(recorded, "NVDA")
    earlier = restatements.as_known_on(result.facts, "2024-03-01")
    shares = [f for f in earlier if f.metric == "shares_diluted" and f.fiscal_period == "FY2024"]
    assert len(shares) == 1
    assert shares[0].value == pytest.approx(2_494_000_000)


def test_unchanged_repetitions_are_not_restatements(recorded):
    """A later 10-K repeats the prior year verbatim. That is not a correction."""
    result = normalize(recorded, "KO")
    revenue = [f for f in result.facts if f.metric == "revenue" and f.fiscal_period == "FY2023"]
    assert len(revenue) == 1


# --------------------------------------------------------------------------
# missing data is unavailable, never zero
# --------------------------------------------------------------------------
def test_missing_metric_produces_a_gap_and_no_fact(recorded):
    """GOOGL tags no GrossProfit. A 0 here would make gross margin 0%."""
    result = normalize(recorded, "GOOGL")
    assert value_of(result, "gross_profit", "FY2025") is None
    assert any("gross_profit" in gap for gap in result.gaps)
    assert all(f.value != 0 or f.metric != "gross_profit" for f in result.facts)


def test_amzn_has_cost_of_revenue_even_without_gross_profit(recorded):
    """The margin is still computable from what IS tagged - by calc/, not here."""
    result = normalize(recorded, "AMZN")
    assert value_of(result, "gross_profit", "FY2025") is None
    assert value_of(result, "cost_of_revenue", "FY2025").value == pytest.approx(356_414_000_000)


def test_bank_metrics_are_absent_rather_than_wrong(recorded):
    result = normalize(recorded, "JPM")
    for metric in ("operating_income", "gross_profit", "capex"):
        assert value_of(result, metric, "FY2025") is None
    assert value_of(result, "revenue", "FY2025").value == pytest.approx(182_447_000_000)


# --------------------------------------------------------------------------
# scope
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("ticker", "level"),
    [
        ("AAPL", "supported"),
        ("NVDA", "supported"),
        ("WDFC", "supported"),
        ("JPM", "partial"),  # SIC 6021, a bank
        ("BRK-B", "partial"),  # SIC 6331, an insurer
        ("O", "partial"),  # SIC 6798, a REIT
        ("TSM", "partial"),  # 20-F, no us-gaap
        ("XOM-HOLDCO", "unsupported"),  # zero 10-Ks under this CIK
    ],
)
def test_scope_levels(recorded, ticker, level):
    companyfacts, submissions = recorded[ticker]
    result = scope.classify(ticker.split("-HOLDCO")[0], submissions, companyfacts, AS_OF)
    assert result.level.value == level
    if level != "supported":
        assert result.reason, "a rejection must name its reason"


def test_partial_still_runs(recorded):
    """A bank is analysable, with its gaps stated. Only unsupported stops."""
    companyfacts, submissions = recorded["JPM"]
    result = scope.classify("JPM", submissions, companyfacts, AS_OF)
    assert result.in_scope is True
    assert result.gaps
    assert result.to_scope().in_scope is True


def test_unknown_ticker_is_a_clean_answer():
    result = scope.classify("ZZZZ", None, None, AS_OF)
    assert result.level is scope.ScopeLevel.UNSUPPORTED
    assert "company_tickers" in result.reason


def test_bad_ticker_shape_is_rejected_before_any_fetch():
    assert scope.classify("../etc/passwd", {}, {}, AS_OF).in_scope is False
    assert scope.classify("", {}, {}, AS_OF).in_scope is False


def test_foreign_issuer_returns_an_empty_result_not_a_crash(recorded):
    """TSM has dei, ifrs-full and srt - no us-gaap node exists."""
    result = normalize(recorded, "TSM")
    assert result.facts == []
    assert result.taxonomy is None
    assert any("foreign" in gap.lower() or "IFRS" in gap for gap in result.gaps)


def test_holding_company_with_no_history_is_unsupported(recorded):
    result = normalize(recorded, "XOM-HOLDCO")
    assert result.facts == []
    assert result.gaps


def test_xom_resolves_to_the_cik_that_holds_the_filings(recorded):
    """The override, and the data that justifies it."""
    assert override_for("XOM").cik == "0000034088"
    result = normalize(recorded, "XOM")
    assert len(result.periods) == 5
    assert value_of(result, "revenue", "FY2025").value > 0


def test_annual_period_count_uses_companyfacts_not_filings_recent(recorded):
    """JPM's filings.recent holds one 10-K across 26,190 rows spanning a year."""
    companyfacts, submissions = recorded["JPM"]
    census = submissions["filings"]["window"]["form_census"]
    assert census.get("10-K", 0) <= 1
    assert scope.annual_period_count(companyfacts, AS_OF) >= 5


# --------------------------------------------------------------------------
# units, signs and dimensions
# --------------------------------------------------------------------------
def test_values_are_full_units_and_scale_is_provenance_only(recorded):
    result = normalize(recorded, "AAPL")
    revenue = value_of(result, "revenue", "FY2025")
    assert revenue.value == pytest.approx(416_161_000_000)
    assert revenue.scale == "units"
    assert revenue.currency == "USD"
    assert revenue.unit.value == "usd"


def test_capex_is_positive_meaning_cash_spent(recorded):
    for ticker in ("AAPL", "NVDA", "KO"):
        result = normalize(recorded, ticker)
        capex = value_of(result, "capex", result.periods[0].label)
        assert capex.value > 0


def test_per_share_and_share_units(recorded):
    result = normalize(recorded, "AAPL")
    assert value_of(result, "eps_diluted", "FY2025").unit.value == "usd_per_share"
    shares = value_of(result, "shares_diluted", "FY2025")
    assert shares.unit.value == "shares"
    assert shares.currency is None


def test_balance_sheet_facts_are_instants(recorded):
    result = normalize(recorded, "AAPL")
    cash = value_of(result, "cash", "FY2025")
    assert cash.period_type.value == "instant"
    assert cash.period_start is None
    revenue = value_of(result, "revenue", "FY2025")
    assert revenue.period_type.value == "duration"
    assert revenue.period_start


def test_companyfacts_carries_no_dimensioned_entries(recorded):
    """Company totals only. The endpoint serves consolidated facts alone."""
    companyfacts, _ = recorded["AAPL"]
    for node in companyfacts["facts"]["us-gaap"].values():
        for entries in node["units"].values():
            assert all(dimensions.is_consolidated(e) for e in entries)


def test_a_dimensioned_fact_would_be_dropped():
    assert dimensions.is_consolidated({"val": 1, "end": "2025-12-31"}) is True
    sliced = {"val": 1, "end": "2025-12-31", "segments": {"Segment": "Americas"}}
    assert dimensions.is_consolidated(sliced) is False
    assert dimensions.consolidated_only([sliced]) == []


# --------------------------------------------------------------------------
# the map itself
# --------------------------------------------------------------------------
def test_ifrs_slot_exists_but_is_empty():
    """Structured for a later IFRS chain; deliberately not built."""
    assert concept_map.IFRS_FULL in concept_map.METRIC_CHAINS
    assert concept_map.METRIC_CHAINS[concept_map.IFRS_FULL] == {}
    assert concept_map.resolve("revenue", {"Revenues": 1}, concept_map.IFRS_FULL) is None


def test_resolve_returns_the_first_hit_in_order():
    available = {"Revenues": "second", "SalesRevenueNet": "third"}
    assert concept_map.resolve("revenue", available) == ("Revenues", "second")
    assert concept_map.resolve("revenue", {}) is None


def test_debt_resolution_prefers_a_reported_total():
    available = {
        "DebtLongtermAndShorttermCombinedAmount": {"val": 100},
        "LongTermDebt": {"val": 90},
        "ShortTermBorrowings": {"val": 10},
    }
    components = concept_map.resolve_total_debt(available)
    assert [c.concept for c in components] == ["DebtLongtermAndShorttermCombinedAmount"]


def test_debt_resolution_skips_debt_current_when_already_covered():
    available = {"LongTermDebt": {"val": 8468}, "DebtCurrent": {"val": 999}}
    assert [c.concept for c in concept_map.resolve_total_debt(available)] == ["LongTermDebt"]


def test_debt_resolution_uses_debt_current_when_not_covered():
    available = {"LongTermDebtNoncurrent": {"val": 86}, "DebtCurrent": {"val": 1}}
    concepts = [c.concept for c in concept_map.resolve_total_debt(available)]
    assert concepts == ["LongTermDebtNoncurrent", "DebtCurrent"]


def test_finance_leases_are_excluded_from_total_debt():
    available = {"LongTermDebt": {"val": 90}, "FinanceLeaseLiability": {"val": 12}}
    concepts = [c.concept for c in concept_map.resolve_total_debt(available)]
    assert "FinanceLeaseLiability" not in concepts


# --------------------------------------------------------------------------
# period helpers
# --------------------------------------------------------------------------
def test_annual_duration_rejects_a_two_year_span():
    assert periods.is_annual_duration("2024-01-01", "2024-12-31") is True
    assert periods.is_annual_duration("2023-01-01", "2024-12-31") is False
    assert periods.is_annual_duration(None, "2024-12-31") is False


def test_label_heuristic_keeps_a_january_year_in_the_previous_year():
    """Only a fallback, but it must not shift a retailer's year by one."""
    assert periods.label("2026-01-31", "01-31", "10-K") == "FY2025"
    assert periods.label("2025-12-31", "12-31", "10-K") == "FY2025"


def test_quarterly_paths_fail_loudly_rather_than_guessing():
    with pytest.raises(NotImplementedError):
        periods.ytd_to_quarterly([], "op_cash_flow")
    with pytest.raises(NotImplementedError):
        periods.derive_q4({}, {})


# --------------------------------------------------------------------------
# stock splits
# --------------------------------------------------------------------------
def test_detector_fires_at_the_nvda_split_boundary(recorded):
    """FY2022's share count was never restated for the 2024 10-for-1 split,
    because no filing after the split still showed FY2022."""
    result = normalize(recorded, "NVDA")
    boundary = [g for g in result.gaps if "share count" in g]
    assert len(boundary) == 1
    assert "FY2022" in boundary[0] and "FY2023" in boundary[0]
    assert "9.9x" in boundary[0]
    assert "totals such as revenue and net income are unaffected" in boundary[0]


def test_detector_is_quiet_when_the_series_is_consistent(recorded):
    for ticker in ("AAPL", "MSFT", "KO", "WDFC"):
        result = normalize(recorded, ticker)
        assert not [g for g in result.gaps if "share count" in g], ticker


def test_reported_split_ratio_becomes_a_citable_fact(recorded):
    result = normalize(recorded, "NVDA")
    ratios = [f for f in result.facts if f.metric == splits.SPLIT_RATIO_METRIC]
    assert len(ratios) == 1
    ratio = ratios[0]
    assert ratio.value == 10.0
    assert ratio.xbrl_concept == "StockholdersEquityNoteStockSplitConversionRatio1"
    assert ratio.source_kind.value == "xbrl_reported"
    assert ratio.accession_number and ratio.filed_at and ratio.source_url


def test_nvda_fy2022_is_split_adjusted_with_full_lineage(recorded):
    """0.385, not 3.85. Arithmetic over two reported facts, both cited."""
    result = normalize(recorded, "NVDA")
    by_metric = {f.metric: f for f in result.facts if f.fiscal_period == "FY2022"}

    eps = by_metric["eps_diluted_split_adjusted"]
    assert eps.value == pytest.approx(0.385)
    assert eps.source_kind.value == "derived"
    assert eps.derivation.computed_by == to_facts.COMPUTED_BY

    shares = by_metric["shares_diluted_split_adjusted"]
    assert shares.value == pytest.approx(25_350_000_000)

    by_id = {f.fact_id: f for f in result.facts}
    inputs = [by_id[i] for i in eps.derivation.input_fact_ids]
    assert {f.metric for f in inputs} == {"eps_diluted", splits.SPLIT_RATIO_METRIC}


def test_the_as_filed_fact_is_left_untouched(recorded):
    """No filing corrected it, so it is not superseded and not rewritten."""
    result = normalize(recorded, "NVDA")
    as_filed = value_of(result, "eps_diluted", "FY2022")
    assert as_filed.value == pytest.approx(3.85)
    assert as_filed.is_current
    assert as_filed.source_kind.value == "xbrl_reported"


def test_adjusted_series_is_continuous(recorded):
    """The point of the exercise: FY2022 now sits next to FY2023."""
    result = normalize(recorded, "NVDA")
    shares = value_of(result, "shares_diluted_split_adjusted", "FY2022").value
    next_year = value_of(result, "shares_diluted", "FY2023").value
    assert 0.9 < shares / next_year < 1.1


def test_only_periods_filed_before_the_split_are_adjusted(recorded):
    """FY2023's current version was filed after the split and already reflects it."""
    result = normalize(recorded, "NVDA")
    adjusted = {f.fiscal_period for f in result.facts if f.metric.endswith(splits.ADJUSTED_SUFFIX)}
    assert adjusted == {"FY2022"}


def test_no_adjustment_without_a_reported_ratio(recorded):
    """The detector's warning stands alone rather than a ratio being guessed."""
    result = normalize(recorded, "AAPL")
    assert not [f for f in result.facts if f.metric.endswith(splits.ADJUSTED_SUFFIX)]


def test_a_run_before_the_split_sees_no_split_at_all(recorded):
    """The ratio was filed 2024-08-28; a run in March 2024 cannot know it."""
    result = normalize(recorded, "NVDA", as_of="2024-03-01")
    assert [e.ratio for e in result.split_events] == [4.0]
    assert not [f for f in result.facts if f.metric.endswith(splits.ADJUSTED_SUFFIX)]
    assert value_of(result, "shares_diluted", "FY2024").value == pytest.approx(2_494_000_000)


def test_one_split_tagged_at_two_dates_is_one_event(recorded):
    """GOOGL tags its 20-for-1 at announcement (2022-02-01) and effect
    (2022-07-15). Two events would multiply a pre-split value by 400."""
    companyfacts, _ = recorded["GOOGL"]
    events = splits.split_events(companyfacts, as_of=AS_OF)
    ratios = [e.ratio for e in events]
    assert ratios.count(20.0) == 1
    twenty = next(e for e in events if e.ratio == 20.0)
    assert twenty.effective_date == "2022-07-15", "the EFFECTIVE date, not the announcement"


def test_nvda_4_for_1_is_not_compounded_to_16(recorded):
    companyfacts, _ = recorded["NVDA"]
    events = splits.split_events(companyfacts, as_of=AS_OF)
    assert [e.ratio for e in events] == [4.0, 10.0]


def test_split_ratio_is_read_from_a_duration_tag_too(recorded):
    """NVDA tagged the 2021 ratio as an instant and the 2024 one as a
    month-long duration. A shape filter loses the one that matters."""
    companyfacts, _ = recorded["NVDA"]
    node = companyfacts["facts"]["us-gaap"]["StockholdersEquityNoteStockSplitConversionRatio1"]
    entries = [e for entries in node["units"].values() for e in entries]
    assert any(e.get("start") for e in entries), "the duration-shaped tag survived recording"
    assert any(e["val"] == 10 for e in entries)


def test_cumulative_ratio_multiplies_later_splits():
    events = [
        splits.SplitEvent("2021-07-19", 4.0, "a", "2021-08-20", "10-Q", "X"),
        splits.SplitEvent("2024-06-30", 10.0, "b", "2024-08-28", "10-Q", "X"),
    ]
    assert splits.cumulative_ratio(events, "2020-01-01") == pytest.approx(40.0)
    assert splits.cumulative_ratio(events, "2022-01-01") == pytest.approx(10.0)
    assert splits.cumulative_ratio(events, "2025-01-01") == pytest.approx(1.0)


def test_a_ratio_below_the_floor_is_ignored():
    """A "ratio" under 1.5 is a rounding or an inverted quote, not a split."""
    payload = {
        "facts": {
            "us-gaap": {
                "StockholdersEquityNoteStockSplitConversionRatio1": {
                    "units": {
                        "pure": [
                            {"end": "2024-01-01", "val": 1.0, "filed": "2024-02-01", "form": "10-K"}
                        ]
                    }
                }
            }
        }
    }
    assert splits.split_events(payload) == []


# --------------------------------------------------------------------------
# when a derived fact became knowable (data/normalize/derived.py)
# --------------------------------------------------------------------------
def _fact(fact_id, filed_at, accession):
    """A minimal reported fact, for exercising the rule without a payload."""
    return FinancialFact(
        fact_id=f"fact:T:m:{fact_id}",
        company_id="T",
        metric="m",
        value=1.0,
        unit="usd",
        currency="USD",
        period_type="instant",
        period_end="2025-12-31",
        fiscal_period="FY2025",
        accession_number=accession,
        filed_at=filed_at,
        retrieved_at="2026-09-19T00:00:00Z",
        source_kind="xbrl_reported",
    )


def test_derived_filed_at_is_the_latest_input_not_the_earliest():
    """The value was not knowable until its LAST input was filed."""
    inputs = [
        _fact("a", "2025-10-30", "0000-1"),
        _fact("b", "2026-02-01", "0000-2"),
        _fact("c", "2025-11-15", "0000-3"),
    ]
    assert derived.filed_at(inputs) == "2026-02-01"


def test_derived_accession_names_the_same_filing_as_the_date():
    """A date from one input and an accession from another is a dead link."""
    inputs = [_fact("a", "2025-10-30", "0000-1"), _fact("b", "2026-02-01", "0000-2")]
    provenance = derived.provenance(inputs)
    assert provenance["filed_at"] == "2026-02-01"
    assert provenance["accession_number"] == "0000-2"


def test_derived_filed_at_breaks_ties_deterministically():
    """Two facts from the same day must not let dict order pick the winner."""
    same_day = [_fact("a", "2026-02-01", "0000-2"), _fact("b", "2026-02-01", "0000-1")]
    assert derived.provenance(same_day)["accession_number"] == "0000-2"
    assert derived.provenance(list(reversed(same_day)))["accession_number"] == "0000-2"


def test_total_debt_is_dated_by_its_last_component(recorded):
    """AAPL's total is summed from components; it is as new as the newest one."""
    result = normalize(recorded, "AAPL")
    by_id = {f.fact_id: f for f in result.facts}
    total = value_of(result, "total_debt", "FY2025")
    assert total.source_kind.value == "derived"

    components = [by_id[i] for i in total.derivation.input_fact_ids]
    assert total.filed_at == max(c.filed_at for c in components)
    assert total.accession_number in {c.accession_number for c in components}


def test_split_adjusted_fact_is_dated_by_the_ratio_not_by_the_value(recorded):
    """The bug this rule exists for.

    NVDA's FY2022 EPS was filed 2024-02-21; the 10-for-1 ratio is first TAGGED
    in a 10-Q filed 2025-05-28. A copy of the as-filed fact inherits the
    February 2024 date, claiming a split-adjusted number was knowable fifteen
    months before we could have computed one.

    The date we use is when the ratio was first tagged in XBRL, which can be
    later than the split's effective date (2024-06-30 here) and later than its
    announcement. That errs in the safe direction: a point-in-time run is never
    shown a number earlier than the data it was computed from existed.
    """
    result = normalize(recorded, "NVDA")
    by_id = {f.fact_id: f for f in result.facts}
    adjusted = value_of(result, "eps_diluted_split_adjusted", "FY2022")
    as_filed = value_of(result, "eps_diluted", "FY2022")

    inputs = [by_id[i] for i in adjusted.derivation.input_fact_ids]
    ratio = next(f for f in inputs if f.metric == splits.SPLIT_RATIO_METRIC)

    assert adjusted.filed_at == ratio.filed_at
    assert adjusted.filed_at > as_filed.filed_at
    assert adjusted.accession_number == ratio.accession_number


def test_a_run_between_the_value_and_the_ratio_sees_no_adjusted_fact(recorded):
    """The point-in-time consequence of the rule, end to end."""
    result = normalize(recorded, "NVDA")
    adjusted = value_of(result, "eps_diluted_split_adjusted", "FY2022")

    day_before = restatements.as_known_on(result.facts, _day_before(adjusted.filed_at))
    assert not [f for f in day_before if f.metric.endswith(splits.ADJUSTED_SUFFIX)]

    on_the_day = restatements.as_known_on(result.facts, adjusted.filed_at)
    assert [f for f in on_the_day if f.metric.endswith(splits.ADJUSTED_SUFFIX)]


def _day_before(iso: str) -> str:
    from datetime import date, timedelta

    return (date.fromisoformat(iso) - timedelta(days=1)).isoformat()


@pytest.mark.parametrize("ticker", OPERATING_COMPANIES)
def test_no_derived_fact_anywhere_is_undated(recorded, ticker):
    """A null filed_at is invisible to the point-in-time filter, so it leaks."""
    result = normalize(recorded, ticker)
    undated = [
        f.fact_id
        for f in result.facts
        if f.source_kind.value == "derived" and not f.filed_at
    ]
    assert undated == []
