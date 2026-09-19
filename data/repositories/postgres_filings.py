"""Postgres FilingRepository with full-text search. MODE=live only.

Specified by schema/contracts/interfaces.py (FilingRepository) and docs/adr/0006.

Search is Postgres `to_tsvector` / `plainto_tsquery` over section text, ALWAYS
scoped by ticker, form, item and filing date. Scoping first is what makes
keyword search sufficient here: by the time the query runs, the candidate set is
a handful of sections from one company, not a corpus.

TODO(roadmap Step 3, P1).
"""

from __future__ import annotations

from schema.contracts.common import ISODate, SectionId, Ticker
from schema.contracts.filings import Filing, FilingSection


class PostgresFilingRepository:
    """FilingRepository backed by the filings and filing_sections tables."""

    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = dsn
        raise NotImplementedError("TODO(roadmap Step 3, P1)")

    def search_filings(
        self, ticker: Ticker, as_of: ISODate, *, forms: list[str] | None = None, limit: int = 20
    ) -> list[Filing]:
        raise NotImplementedError("TODO(roadmap Step 3, P1)")

    def get_section(self, section_id: SectionId, as_of: ISODate) -> FilingSection | None:
        """Returns None when the section was filed after `as_of`, never the text."""
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
        """Scope first (ticker, form, item, filed_at <= as_of), then rank by ts_rank."""
        raise NotImplementedError("TODO(roadmap Step 3, P1)")

    def put_filing(self, filing: Filing, sections: list[FilingSection]) -> int:
        raise NotImplementedError("TODO(roadmap Step 3, P1)")
