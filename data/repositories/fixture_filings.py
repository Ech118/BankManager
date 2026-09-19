"""Fixture-backed FilingRepository. Powers MODE=mock with no database.

Specified by schema/contracts/interfaces.py (FilingRepository).

Search is a naive substring match over the fixture sections. That is fine for a
mock: the CONTRACT being exercised is "scoped search returns whole structural
sections", not the ranking quality.

TODO(roadmap Step 3, P1).
"""

from __future__ import annotations

from schema.contracts.common import ISODate, SectionId, Ticker
from schema.contracts.filings import Filing, FilingSection


class FixtureFilingRepository:
    """In-memory FilingRepository over fixtures/mock/."""

    def __init__(self, fixtures_dir: str | None = None) -> None:
        self.fixtures_dir = fixtures_dir
        raise NotImplementedError("TODO(roadmap Step 3, P1): load filings.json")

    def search_filings(
        self, ticker: Ticker, as_of: ISODate, *, forms: list[str] | None = None, limit: int = 20
    ) -> list[Filing]:
        raise NotImplementedError("TODO(roadmap Step 3, P1)")

    def get_section(self, section_id: SectionId, as_of: ISODate) -> FilingSection | None:
        raise NotImplementedError("TODO(roadmap Step 3, P1)")

    def search_sections(
        self,
        ticker: Ticker,
        query: str,
        as_of: ISODate,
        *,
        forms: list[str] | None = None,
        items: list[str] | None = None,
        limit: int = 10,
    ) -> list[FilingSection]:
        raise NotImplementedError("TODO(roadmap Step 3, P1)")

    def put_filing(self, filing: Filing, sections: list[FilingSection]) -> int:
        raise NotImplementedError("TODO(roadmap Step 3, P1)")
