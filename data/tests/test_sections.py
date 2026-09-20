"""10-K Item 1 and 1A extraction, against five recorded real filings.

Offline: `python -m data.record.sections` captured each filing's plain text
once. The HTML-to-text conversion is tested separately against small documents
written here, where a specific tag behaviour can be asserted rather than
inferred from a 1.4MB file.

Each filing is here because it breaks a different plausible parser:

  AAPL  the ordinary case.
  NVDA  says "see Item 1A. Risk Factors' for a discussion of these risks" 6,000
        characters before the real section. Taking the first match that has a
        body returns 121KB of real content starting in the wrong place.
  KO    puts a cross-reference to Item 8 between its Item 1 and its Item 1A, and
        mentions "Item 1. Business" five more times inside the body.
  JPM   a 12.9MB filing whose contents block holds four Item headings within 930
        characters, and which cross-references "Item 1A: Risk Factors" four
        times, once 590KB from the end of the document.
  MSFT  letter-spaces its headings: the text reads "ITEM 1. B USINESS" and
        "ITEM 1A. RIS K FACTORS". No regex over the visible text matches those.
"""

from __future__ import annotations

import pytest

from data.record.sections import load
from data.sections import parser
from schema.contracts.enums import ItemCode
from schema.contracts.filings import Filing, FilingSection

TICKERS = ["AAPL", "NVDA", "KO", "JPM", "MSFT"]
WANTED = (ItemCode.BUSINESS, ItemCode.RISK_FACTORS)


@pytest.fixture(scope="module")
def recorded():
    return {ticker: load(ticker) for ticker in TICKERS}


def filing_for(meta: dict) -> Filing:
    return Filing(
        accession=meta["accession"],
        company_id=meta["ticker"],
        cik=meta["cik"],
        form="10-K",
        fiscal_period="FY2025",
        period_end=meta["period_end"],
        filed_at=meta["filed_at"],
        retrieved_at="2026-09-20T00:00:00Z",
    )


_SPLITS: dict[str, tuple] = {}


def split_for(recorded, ticker):
    """Cached: splitting five filings once per test run, not once per test."""
    if ticker not in _SPLITS:
        text, meta = recorded[ticker]
        _SPLITS[ticker] = (parser.split(filing_for(meta), text, wanted=WANTED), text)
    return _SPLITS[ticker]


# --------------------------------------------------------------------------
# both sections come out, for every filer
# --------------------------------------------------------------------------
@pytest.mark.parametrize("ticker", TICKERS)
def test_item_1_and_1a_are_both_extracted(recorded, ticker):
    result, _ = split_for(recorded, ticker)
    assert {s.item for s in result.sections} == set(WANTED), (
        f"{ticker}: got {[s.item.value for s in result.sections]}"
    )


@pytest.mark.parametrize("ticker", TICKERS)
def test_each_section_starts_at_its_own_heading(recorded, ticker):
    """Not mid-sentence, and not at a contents line."""
    result, _ = split_for(recorded, ticker)
    for section in result.sections:
        squashed = "".join(section.text[:60].lower().split())
        expected = "item1a" if section.item is ItemCode.RISK_FACTORS else "item1"
        assert squashed.startswith(expected), (
            f"{ticker} {section.item.value} starts {section.text[:60]!r}"
        )


@pytest.mark.parametrize("ticker", TICKERS)
def test_sections_are_long_enough_to_be_real(recorded, ticker):
    """A contents line is tens of characters; a real Item is tens of thousands."""
    result, _ = split_for(recorded, ticker)
    for section in result.sections:
        assert section.char_count > 10_000, (
            f"{ticker} {section.item.value} is only {section.char_count} chars"
        )


@pytest.mark.parametrize("ticker", TICKERS)
def test_item_1a_does_not_swallow_the_rest_of_the_filing(recorded, ticker):
    """Item 1A ends at Item 1B/1C/2/3. Without a terminator it would run to the
    end of the document and carry the financial statements with it."""
    result, text = split_for(recorded, ticker)
    risk = next(s for s in result.sections if s.item is ItemCode.RISK_FACTORS)
    assert risk.char_count < len(text) * 0.6, (
        f"{ticker}: Item 1A is {risk.char_count} of {len(text)} characters"
    )


def test_msft_letter_spaced_headings_are_found(recorded):
    """The text genuinely reads "ITEM 1. B USINESS"."""
    result, _ = split_for(recorded, "MSFT")
    business = next(s for s in result.sections if s.item is ItemCode.BUSINESS)
    assert "B USINESS" in business.text[:40]


def test_nvda_skips_the_cross_reference_before_the_real_section(recorded):
    """NVIDIA mentions Item 1A mid-sentence before the section itself."""
    result, _ = split_for(recorded, "NVDA")
    risk = next(s for s in result.sections if s.item is ItemCode.RISK_FACTORS)
    assert not risk.text[:200].lower().startswith("item 1a. risk factors  for")
    assert "risk factors" in risk.text[:60].lower()


def test_jpm_contents_block_does_not_win(recorded):
    """Four Item headings inside 930 characters are a list, not four sections."""
    result, _ = split_for(recorded, "JPM")
    for section in result.sections:
        assert section.char_start > 240_000, (
            f"JPM {section.item.value} starts at {section.char_start}, in the "
            "contents block"
        )


# --------------------------------------------------------------------------
# offsets are the product
# --------------------------------------------------------------------------
@pytest.mark.parametrize("ticker", TICKERS)
def test_offsets_index_into_the_document_they_came_from(recorded, ticker):
    """A verifier locates a quote with these. If they are off by a character
    the string match fails and a true claim is reported unsupported."""
    result, text = split_for(recorded, ticker)
    for section in result.sections:
        assert text[section.char_start : section.char_end] == section.text


@pytest.mark.parametrize("ticker", TICKERS)
def test_the_contract_offset_invariant_holds(recorded, ticker):
    result, _ = split_for(recorded, ticker)
    for section in result.sections:
        assert section.char_end - section.char_start == section.char_count
        assert section.char_count == len(section.text)
        FilingSection.model_validate(section.model_dump())


@pytest.mark.parametrize("ticker", TICKERS)
def test_sections_do_not_overlap(recorded, ticker):
    result, _ = split_for(recorded, ticker)
    spans = sorted((s.char_start, s.char_end) for s in result.sections)
    for (_, end), (start, _) in zip(spans, spans[1:], strict=False):
        assert end <= start


@pytest.mark.parametrize("ticker", TICKERS)
def test_ids_are_deterministic(recorded, ticker):
    result, _ = split_for(recorded, ticker)
    _, meta = recorded[ticker]
    for section in result.sections:
        assert section.section_id == f"sec:{meta['accession']}:{section.item.value}"
        assert section.source_id == f"src:edgar_text:{meta['accession']}:{section.item.value}"


@pytest.mark.parametrize("ticker", TICKERS)
def test_extraction_is_reproducible(recorded, ticker):
    """Two runs over the same document must agree, or offsets are meaningless.

    Deliberately bypasses split_for's cache - comparing a cached result with
    itself would pass whatever the parser did.
    """
    text, meta = recorded[ticker]
    first = parser.split(filing_for(meta), text, wanted=WANTED)
    second = parser.split(filing_for(meta), text, wanted=WANTED)
    assert [(s.section_id, s.char_start, s.char_count) for s in first.sections] == [
        (s.section_id, s.char_start, s.char_count) for s in second.sections
    ]


# --------------------------------------------------------------------------
# a section that looks wrong is not returned
# --------------------------------------------------------------------------
def test_a_document_with_only_a_contents_block_yields_nothing():
    """Better no section than a contents line quoted as a risk factor."""
    text = "\n".join(
        [
            "TABLE OF CONTENTS",
            "Item 1. Business 3",
            "Item 1A. Risk Factors 12",
            "Item 1B. Unresolved Staff Comments 30",
            "Item 2. Properties 31",
        ]
    )
    filing = filing_for(
        {
            "accession": "0000000000-26-000001",
            "ticker": "ACME",
            "cik": "0000000001",
            "period_end": "2025-12-31",
            "filed_at": "2026-02-01",
        }
    )
    result = parser.split(filing, text, wanted=WANTED)
    assert result.sections == []
    assert result.gaps


def test_a_document_with_no_headings_reports_a_gap():
    filing = filing_for(
        {
            "accession": "0000000000-26-000002",
            "ticker": "ACME",
            "cik": "0000000001",
            "period_end": "2025-12-31",
            "filed_at": "2026-02-01",
        }
    )
    result = parser.split(filing, "Nothing structural here at all. " * 200, wanted=WANTED)
    assert result.sections == []
    assert any("no Item heading" in g for g in result.gaps)


def test_a_short_section_is_dropped_with_a_reason():
    body = "Item 1. Business\n\n" + ("Real prose. " * 40)  # under MIN_SECTION_CHARS
    filing = filing_for(
        {
            "accession": "0000000000-26-000003",
            "ticker": "ACME",
            "cik": "0000000001",
            "period_end": "2025-12-31",
            "filed_at": "2026-02-01",
        }
    )
    result = parser.split(filing, body, wanted=WANTED)
    assert result.sections == []


# --------------------------------------------------------------------------
# HTML to text
# --------------------------------------------------------------------------
def test_block_tags_become_line_breaks_so_headings_stand_alone():
    text = parser.to_plain_text("<p>Item 1. Business</p><p>We make things.</p>")
    assert "Item 1. Business\n\nWe make things." in text


def test_inline_tags_become_spaces_so_words_do_not_merge():
    assert "hello world" in parser.to_plain_text("<span>hello</span><b>world</b>")


def test_script_and_style_are_dropped():
    text = parser.to_plain_text("<style>p{color:red}</style><p>Real text</p><script>x=1</script>")
    assert "color" not in text and "x=1" not in text
    assert "Real text" in text


def test_entities_are_unescaped():
    assert "AT&T" in parser.to_plain_text("<p>AT&amp;T</p>")


def test_non_breaking_spaces_become_ordinary_ones():
    """They are everywhere in EDGAR HTML and would otherwise defeat every
    heading regex."""
    text = parser.to_plain_text("<p>Item&nbsp;1.&nbsp;Business</p>")
    assert "\xa0" not in text


def test_conversion_is_deterministic():
    """Offsets are stored against this output, so it must not vary by run."""
    html = "<div>Item 1. Business</div><div>Body text here.</div>" * 20
    assert parser.to_plain_text(html) == parser.to_plain_text(html)


def test_bytes_and_str_convert_identically():
    html = "<p>Item 1. Business</p>"
    assert parser.to_plain_text(html.encode("utf-8")) == parser.to_plain_text(html)


# --------------------------------------------------------------------------
# the squashed matcher
# --------------------------------------------------------------------------
def test_squash_maps_offsets_back_to_the_real_document():
    text = "  Hello\n\n  World  "
    squashed, offsets = parser.squash(text)
    assert squashed == "helloworld"
    assert text[offsets[0]] == "H"
    assert text[offsets[5]] == "W"


def test_a_heading_inside_a_sentence_is_not_a_heading():
    line = "Please see Item 1A. Risk Factors for more detail."
    assert not parser.starts_a_line(line, line.index("Item"))


def test_a_heading_on_its_own_line_is_a_heading():
    text = "Some prose.\nItem 1A. Risk Factors\nThe following..."
    assert parser.starts_a_line(text, text.index("Item 1A"))
