"""Segment/dimension handling: consolidated totals vs sliced facts.

Specified by docs/sec-pitfalls.md "Dimensions vs totals".

An XBRL fact may be dimensioned (a segment, a geography, a product line) or
consolidated. Summing dimensioned facts to reconstruct a total is wrong: the
axes overlap, some segments are omitted, and eliminations are missing. The
consolidated total is the fact with NO dimensions, and that is the only one that
may be used as a company-level number.

WHAT THE REAL DATA SHOWS
    `companyfacts` carries no dimensioned facts at all. Across AAPL, JPM, NVDA
    and O, the union of keys on every entry is exactly:

        accn, end, filed, form, fp, frame, fy, start, val

    There is no axis or member anywhere, because the endpoint serves only the
    consolidated total for each concept. So company-level normalization is safe
    by construction, and the filter below is a guard against a future source
    (a filing's own XBRL instance, or companyconcept with dimensions) rather
    than a working part of today's path.

    The cost is that a dimensioned-only disclosure VANISHES instead of arriving
    sliced - which is how GOOGL loses dei:EntityCommonStockSharesOutstanding
    entirely, since Alphabet tags it per share class
    (see data/ingest/market_client.py).
"""

from __future__ import annotations

DIMENSION_KEYS: tuple[str, ...] = ("segments", "dimensions", "dim", "members", "axis")
"""Keys a dimensioned fact would carry. None of them appear in companyfacts."""


def is_consolidated(fact: dict) -> bool:
    """True when a raw XBRL fact carries no dimension members."""
    return not any(fact.get(key) for key in DIMENSION_KEYS)


def consolidated_only(facts: list[dict]) -> list[dict]:
    """Drop every dimensioned fact. Used for all company-level metrics."""
    return [fact for fact in facts if is_consolidated(fact)]


def parse_dimension(fact: dict) -> dict[str, str] | None:
    """Axis -> member for a dimensioned fact, or None when consolidated."""
    for key in DIMENSION_KEYS:
        value = fact.get(key)
        if isinstance(value, dict) and value:
            return {str(k): str(v) for k, v in value.items()}
    return None
