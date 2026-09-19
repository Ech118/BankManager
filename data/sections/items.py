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
