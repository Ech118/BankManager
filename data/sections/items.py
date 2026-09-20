"""Canonical section names and the heading patterns that find them.

Specified by docs/data-model.md "Filing sections".

Headings vary in wording and capitalisation between filers and years, so each
canonical ItemCode owns a list of patterns. Anything unmatched becomes OTHER
rather than being dropped, so no text disappears silently.

TODO(roadmap Step 3, P1): extend the patterns against real filings.
"""

from __future__ import annotations

from schema.contracts.enums import ItemCode

ITEM_PATTERNS: dict[ItemCode, tuple[str, ...]] = {
    ItemCode.BUSINESS: (r"item\s*1\s*[.\-:]?\s*business",),
    ItemCode.RISK_FACTORS: (r"item\s*1a\s*[.\-:]?\s*risk\s*factors",),
    ItemCode.MDNA: (
        r"item\s*7\s*[.\-:]?\s*management'?s?\s*discussion",
        r"item\s*2\s*[.\-:]?\s*management'?s?\s*discussion",  # 10-Q numbering
    ),
    ItemCode.FINANCIAL_STATEMENTS: (r"item\s*8\s*[.\-:]?\s*financial\s*statements",),
    ItemCode.CONTROLS: (r"item\s*9a\s*[.\-:]?\s*controls\s*and\s*procedures",),
}
"""Item heading patterns, matched case-insensitively against normalized text."""

SQUASHED_ITEM_PATTERNS: dict[ItemCode, tuple[str, ...]] = {
    ItemCode.BUSINESS: (r"item1[.\-:]?business",),
    ItemCode.RISK_FACTORS: (r"item1a[.\-:]?riskfactors",),
    ItemCode.MDNA: (
        r"item7[.\-:]?management'?s?discussion",
        r"item2[.\-:]?management'?s?discussion",  # 10-Q numbering
    ),
    ItemCode.FINANCIAL_STATEMENTS: (r"item8[.\-:]?financialstatements",),
    ItemCode.CONTROLS: (r"item9a[.\-:]?controlsandprocedures",),
}
"""The same headings, written to match text with ALL whitespace removed.

Filers letter-space their headings with markup: Microsoft's FY2026 10-K renders
"ITEM 1. B USINESS" and "INFORMATION ABOUT OUR EXECUTIV E OFFICERS", because the
styling that spaces the capitals survives the tag stripping as real spaces. No
pattern over the visible text can match that without enumerating where the gaps
fall, which differs per filer and per year.

Matching a whitespace-free copy and mapping the offset back handles letter
spacing, line breaks inside a heading, and non-breaking spaces in one move, and
costs one pass over the document. ITEM_PATTERNS above is kept for callers that
want to match the visible text."""


SQUASHED_TERMINATORS: tuple[str, ...] = (
    r"item1b[.\-:]?unresolvedstaffcomments",
    r"item1c[.\-:]?cybersecurity",
    r"item2[.\-:]?properties",
    r"item3[.\-:]?legalproceedings",
)
"""Headings that END Item 1A, matched against the whitespace-free text.

Item 1A cannot be ended by "the next Item heading we recognise", because a risk
factors section cross-references Item 1 and Item 8 inside its own body -
Coca-Cola's does it twice in the first 5,000 characters. Ending there truncates
the section to a fraction of itself while looking entirely successful.

What genuinely follows Item 1A in a 10-K is Item 1B, 1C, 2 or 3, and none of
those is a phrase a risk factor uses in passing."""


NOTE_PATTERNS: dict[ItemCode, tuple[str, ...]] = {
    ItemCode.DEBT_NOTE: (r"note\s*\d+\s*[.\-:]?\s*(long-?term\s*)?debt", r"\bborrowings\b"),
    ItemCode.SBC_NOTE: (r"note\s*\d+\s*[.\-:]?\s*(share|stock)-?based\s*compensation",),
    ItemCode.SEGMENTS_NOTE: (r"note\s*\d+\s*[.\-:]?\s*segment",),
    ItemCode.REVENUE_NOTE: (r"note\s*\d+\s*[.\-:]?\s*revenue",),
}
"""Notes to the financial statements, nested inside FINANCIAL_STATEMENTS."""

AGENT_SECTIONS: dict[str, tuple[ItemCode, ...]] = {
    "financial": (ItemCode.MDNA, ItemCode.FINANCIAL_STATEMENTS, ItemCode.SBC_NOTE,
                  ItemCode.DEBT_NOTE, ItemCode.REVENUE_NOTE),
    "business": (ItemCode.BUSINESS, ItemCode.RISK_FACTORS, ItemCode.SEGMENTS_NOTE),
    "valuation": (ItemCode.MDNA, ItemCode.SEGMENTS_NOTE),
    "red_team": (ItemCode.RISK_FACTORS, ItemCode.DEBT_NOTE, ItemCode.MDNA),
}
"""Which sections each agent is given by default, to control cost (error K)."""


def classify(heading: str) -> ItemCode:
    """Map a raw filing heading to a canonical ItemCode, or OTHER."""
    raise NotImplementedError("TODO(roadmap Step 3, P1)")
