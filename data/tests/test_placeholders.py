"""P1 unit-test placeholders. Each becomes a real test at the named roadmap step.

Step 0 ships no logic, so these are skipped with a reason rather than deleted:
the skip list is the shortest readable statement of what P1 owes the project.
"""

import pytest


@pytest.mark.skip(reason="TODO(roadmap Step 1, P1): EDGAR client + concept mapping")
def test_concept_map_resolves_revenue_across_tag_variants():
    """revenue must resolve whether a filer uses Revenues or the ASC 606 tag,
    and the winning tag must be recorded on the fact."""


@pytest.mark.skip(reason="TODO(roadmap Step 1, P1): check_scope")
def test_check_scope_rejects_banks_reits_and_pre_revenue():
    """Rejection must carry a human-readable reason, not a bare False."""


@pytest.mark.skip(reason="TODO(roadmap Step 2, P1): YTD differencing")
def test_ytd_cash_flow_is_differenced_into_quarters():
    """Q3 operating cash flow is Q3-YTD minus Q2-YTD, never the raw YTD figure."""


@pytest.mark.skip(reason="TODO(roadmap Step 2, P1): Q4 derivation")
def test_q4_is_derived_as_fy_minus_nine_month_ytd():
    """There is no Q4 filing; the derived fact must carry a Derivation."""


@pytest.mark.skip(reason="TODO(roadmap Step 2, P1): restatements")
def test_restated_fact_is_superseded_not_overwritten():
    """Both rows survive; the old one gets superseded_by, and a point-in-time
    query before the restatement still returns the as-filed value."""


@pytest.mark.skip(reason="TODO(roadmap Step 2, P1): point-in-time")
def test_point_in_time_query_excludes_later_filings():
    """The single most important P1 behaviour: an as_of run must never see a
    filing filed after that date (error A)."""


@pytest.mark.skip(reason="TODO(roadmap Step 3, P1): section parsing")
def test_sections_split_on_items_not_token_windows():
    """Offsets must round-trip: text[char_start:char_end] is the section."""


@pytest.mark.skip(reason="TODO(roadmap Step 3, P1): section parsing")
def test_table_of_contents_headings_are_not_mistaken_for_sections():
    """A 10-K repeats every Item heading in its table of contents."""


@pytest.mark.skip(reason="TODO(roadmap Step 1, P1): dimensions")
def test_dimensioned_facts_are_never_summed_into_a_total():
    """Only the undimensioned fact is the consolidated total."""


@pytest.mark.skip(reason="TODO(roadmap Step 4, P1): market client")
def test_failed_market_fetch_degrades_to_unavailable():
    """A provider outage must produce an unavailable ValueObject and a
    data_quality gap, never a 0 and never a guess."""
