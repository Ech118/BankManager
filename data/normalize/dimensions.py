"""Segment/dimension handling: consolidated totals vs sliced facts.

Specified by docs/sec-pitfalls.md "Dimensions vs totals".

An XBRL fact may be dimensioned (a segment, a geography, a product line) or
consolidated. Summing dimensioned facts to reconstruct a total is wrong: the
axes overlap, some segments are omitted, and eliminations are missing. The
consolidated total is the fact with NO dimensions, and that is the only one that
may be used as a company-level number.

TODO(roadmap Step 1, P1): implement; TODO(roadmap Step 3, P1): expose segments.
"""

from __future__ import annotations


def is_consolidated(fact: dict) -> bool:
    """True when a raw XBRL fact carries no dimension members."""
    raise NotImplementedError("TODO(roadmap Step 1, P1)")


def consolidated_only(facts: list[dict]) -> list[dict]:
    """Drop every dimensioned fact. Used for all company-level metrics."""
    raise NotImplementedError("TODO(roadmap Step 1, P1)")


def parse_dimension(fact: dict) -> dict[str, str] | None:
    """Axis -> member for a dimensioned fact, or None when consolidated."""
    raise NotImplementedError("TODO(roadmap Step 3, P1)")
