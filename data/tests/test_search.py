"""Ranked keyword search over filing sections.

Offline: the sections are built here rather than fetched, so the ranking is
tested against text whose statistics we control. The fixture-backed path is
covered by mcp_server/tests.
"""

from __future__ import annotations

import pytest

from data.sections import search as section_search
from schema.contracts.filings import FilingSection

AS_OF = "2026-09-19"


def section(section_id, text, *, item="risk_factors", form="10-K", filed_at="2026-02-01"):
    return FilingSection.model_validate(
        {
            "section_id": section_id,
            "source_id": f"src:edgar_text:{section_id.replace(':', '_')}",
            "company_id": "ACME",
            "accession": "0000000000-26-000001",
            "form": form,
            "fiscal_period": f"FY{filed_at[:4]}",
            "item": item,
            "filed_at": filed_at,
            "heading_path": ["Item 1A", "Risk Factors"],
            "char_start": 0,
            "char_end": len(text),
            "char_count": len(text),
            "text": text,
        }
    )


def run(sections, query, **kwargs):
    return section_search.search(
        sections, [s.text for s in sections], query, **kwargs
    )


# --------------------------------------------------------------------------
# ranking
# --------------------------------------------------------------------------
def test_a_section_without_any_query_term_is_dropped():
    """The best of a bad set, unlabelled, is how an agent quotes the wrong
    section with confidence."""
    sections = [
        section("sec:a:risk_factors", "our debt covenants restrict additional borrowing"),
        section("sec:b:compensation", "executive compensation is set by the committee"),
    ]
    hits = run(sections, "debt covenants")
    assert [h.section_id for h in hits] == ["sec:a:risk_factors"]


def test_the_longest_section_does_not_win_by_default():
    """Substring matching would return both and order them arbitrarily; BM25
    normalizes by length, so a focused section beats a sprawling one."""
    focused = section("sec:focused:risk_factors", "covenant covenant covenant leverage")
    sprawling = section(
        "sec:sprawling:risk_factors", "covenant " + ("unrelated prose about widgets " * 400)
    )
    hits = run([sprawling, focused], "covenant")
    assert hits[0].section_id == "sec:focused:risk_factors"


def test_a_term_in_every_section_does_not_decide_the_ranking():
    """idf near zero for a ubiquitous word. Otherwise 'company' - which appears
    in every section of every filing - would dominate every query."""
    sections = [
        section("sec:a:risk_factors", "the company discusses semiconductor supply"),
        section("sec:b:business", "the company discusses retail stores"),
    ]
    hits = run(sections, "company semiconductor")
    assert hits[0].section_id == "sec:a:risk_factors"


def test_repeating_a_term_saturates():
    """Twenty mentions is not ten times better than two - K1 caps it. Without
    saturation a keyword-stuffed section outranks a substantive one."""
    few = section("sec:few:risk_factors", "tariff " + "filler " * 20)
    many = section("sec:many:risk_factors", "tariff " * 20 + "filler " * 20)
    hits = run([few, many], "tariff")
    ratio = hits[0].score / hits[1].score
    assert 1.0 < ratio < 4.0


def test_ties_break_deterministically():
    """Two runs over the same corpus must agree, whatever order it loaded in."""
    a = section("sec:a:risk_factors", "identical text about leverage")
    b = section("sec:b:risk_factors", "identical text about leverage")
    assert [h.section_id for h in run([a, b], "leverage")] == ["sec:a:risk_factors", "sec:b:risk_factors"]
    assert [h.section_id for h in run([b, a], "leverage")] == ["sec:a:risk_factors", "sec:b:risk_factors"]


def test_matched_terms_are_reported():
    """An agent that cannot see why a section ranked cannot judge the hit."""
    sections = [section("sec:a:risk_factors", "supply chain concentration in taiwan")]
    hit = run(sections, "taiwan concentration missingword")[0]
    assert set(hit.matched_terms) == {"taiwan", "concentration"}


# --------------------------------------------------------------------------
# queries that should not explode
# --------------------------------------------------------------------------
def test_an_all_stopword_query_returns_nothing_rather_than_everything():
    sections = [section("sec:a:risk_factors", "the company and its subsidiaries")]
    assert run(sections, "the and of") == []


def test_an_empty_query_returns_nothing():
    sections = [section("sec:a:risk_factors", "anything at all")]
    assert run(sections, "") == []


def test_no_sections_is_an_empty_result_not_an_error():
    assert section_search.search([], [], "debt") == []


def test_search_is_case_insensitive():
    sections = [section("sec:a:risk_factors", "Concentration of Credit Risk")]
    assert len(run(sections, "CREDIT concentration")) == 1


# --------------------------------------------------------------------------
# scoping
# --------------------------------------------------------------------------
def test_a_section_filed_after_as_of_is_never_returned():
    """ADR 0003. A backtest that reads next year's 10-K is not a backtest."""
    sections = [
        section("sec:old:risk_factors", "supply chain risk", filed_at="2025-02-01"),
        section("sec:new:risk_factors", "supply chain risk", filed_at="2026-02-01"),
    ]
    hits = run(sections, "supply chain", as_of="2025-06-01")
    assert [h.section_id for h in hits] == ["sec:old:risk_factors"]


def test_form_and_item_filters_apply():
    sections = [
        section("sec:a:risk_factors", "inventory obsolescence", item="risk_factors", form="10-K"),
        section("sec:b:mdna", "inventory obsolescence", item="mdna", form="10-Q"),
    ]
    assert [h.section_id for h in run(sections, "inventory", forms=["10-Q"])] == [
        "sec:b:mdna"
    ]
    assert [h.section_id for h in run(sections, "inventory", items=["risk_factors"])] == [
        "sec:a:risk_factors"
    ]


def test_filtering_happens_before_ranking():
    """The idf must reflect what was searchable at as_of, not what exists now.

    Here 'covenant' is in every section today, so its idf today is near zero.
    Scoped to 2025 it appears in one of two, and must still rank that one.
    """
    sections = [
        section("sec:a:risk_factors", "covenant leverage test", filed_at="2025-02-01"),
        section("sec:b:risk_factors", "unrelated prose", filed_at="2025-02-01"),
        section("sec:c:risk_factors", "covenant covenant", filed_at="2026-02-01"),
        section("sec:d:risk_factors", "covenant covenant", filed_at="2026-02-01"),
    ]
    hits = run(sections, "covenant", as_of="2025-06-01")
    assert [h.section_id for h in hits] == ["sec:a:risk_factors"]
    assert hits[0].score > 0


def test_limit_caps_the_result():
    sections = [section(f"sec:{i}:risk_factors", "liquidity risk") for i in range(8)]
    assert len(run(sections, "liquidity", limit=3)) == 3


# --------------------------------------------------------------------------
# whole sections, not fragments (ADR 0006)
# --------------------------------------------------------------------------
def test_the_returned_text_is_the_whole_section_verbatim():
    text = "Item 1A. Risk Factors. " + ("our supply chain is concentrated. " * 50)
    sections = [section("sec:a:risk_factors", text)]
    hit = run(sections, "supply chain")[0]
    assert hit.section.text == text
    assert hit.section.char_count == len(text)


def test_tokenizer_drops_single_characters_and_stopwords():
    assert section_search.tokenize("The a b debt of X") == ["debt"]


def test_scores_are_reproducible():
    """A verifier that cannot recompute a score cannot audit it."""
    sections = [section("sec:a:risk_factors", "goodwill impairment charge")]
    first = run(sections, "impairment")[0].score
    second = run(sections, "impairment")[0].score
    assert first == pytest.approx(second)
