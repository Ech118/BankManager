"""Fixture-backed FilingRepository. Powers MODE=mock with no database.

Specified by schema/contracts/interfaces.py (FilingRepository) and ADR 0006.

Filings are split by STRUCTURE, never chunk-and-embed: each section is a whole
Item or note, keyed by section_id, carrying character offsets into the source
document and its text verbatim.

TWO FIXTURE FILES MAKE ONE SECTION
    fixtures/mock/factsheet.json  filing_sections[]  metadata, with text: ""
    fixtures/mock/sections/<item>.txt                 the prose

They are joined here. The text lives in .txt files so the prose stays readable
and diffable rather than being buried in a JSON string.

LINE ENDINGS
    The fixtures were authored with LF, and the declared char_count assumes LF.
    A Windows clone checks them out as CRLF, which would make len(text) exceed
    char_count and fail the FilingSection validator. Normalising to LF here is
    what makes the same char_count correct on every platform.
"""

from __future__ import annotations

import json
from pathlib import Path

from schema.contracts.common import ISODate, SectionId, Ticker
from schema.contracts.filings import Filing, FilingSection

_DEFAULT_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "mock"


class FixtureFilingRepository:
    """In-memory FilingRepository over the ACME fixtures."""

    def __init__(self, fixtures_dir: str | Path | None = None) -> None:
        self.fixtures_dir = Path(fixtures_dir) if fixtures_dir else _DEFAULT_FIXTURES
        self._filings: list[Filing] = [
            Filing.model_validate(f) for f in self._load("filings.json")
        ]
        self._sections: dict[str, FilingSection] = {}
        for raw in self._load("factsheet.json")["filing_sections"]:
            section = FilingSection.model_validate({**raw, "text": self._text_for(raw)})
            self._sections[section.section_id] = section

    def _load(self, name: str):
        return json.loads((self.fixtures_dir / name).read_text(encoding="utf-8"))

    def _text_for(self, raw: dict) -> str:
        """Prose for one section, or "" when no .txt file accompanies it.

        The section_id suffix is the file stem: sec:<accession>:mdna -> mdna.txt.
        """
        path = self.fixtures_dir / "sections" / f"{raw['section_id'].rsplit(':', 1)[-1]}.txt"
        if not path.exists():
            return ""
        return path.read_bytes().decode("utf-8").replace("\r\n", "\n")

    # ------------------------------------------------------------------
    # FilingRepository
    # ------------------------------------------------------------------
    def search_filings(
        self,
        ticker: Ticker,
        as_of: ISODate,
        *,
        forms: list[str] | None = None,
        limit: int = 20,
    ) -> list[Filing]:
        """Filings filed on or before `as_of`, newest first."""
        wanted = {str(f) for f in forms} if forms else None
        rows = [
            f
            for f in self._filings
            if f.company_id == ticker
            and (not as_of or f.filed_at <= as_of)
            and (wanted is None or str(f.form) in wanted)
        ]
        rows.sort(key=lambda f: (f.filed_at, f.accession), reverse=True)
        return rows[:limit] if limit else rows

    def get_section(self, section_id: SectionId, as_of: ISODate) -> FilingSection | None:
        """One parsed section verbatim, or None when unknown or not yet filed."""
        section = self._sections.get(section_id)
        if section is None or (as_of and section.filed_at > as_of):
            return None
        return section

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
        """Naive substring match. Postgres full-text search replaces this later.

        Deliberately not ranked: a fixture of five sections cannot demonstrate
        relevance ordering, and a fake ranking here would hide the fact that the
        real one does not exist yet.
        """
        needle = query.lower()
        wanted_forms = {str(f) for f in forms} if forms else None
        wanted_items = {str(i) for i in items} if items else None
        rows = [
            s
            for s in self._sections.values()
            if s.company_id == ticker
            and (not as_of or s.filed_at <= as_of)
            and (wanted_forms is None or str(s.form) in wanted_forms)
            and (wanted_items is None or str(s.item) in wanted_items)
            and needle in s.text.lower()
        ]
        rows.sort(key=lambda s: (s.filed_at, s.section_id), reverse=True)
        return rows[:limit] if limit else rows

    def put_filing(self, filing: Filing, sections: list[FilingSection]) -> int:
        """The fixture store is read-only; live ingestion writes to Postgres."""
        raise NotImplementedError(
            "FixtureFilingRepository is read-only. Regenerate the fixtures with "
            "`make gen-mock`, or use PostgresFilingRepository in MODE=live."
        )

    # ------------------------------------------------------------------
    # Beyond the Protocol
    # ------------------------------------------------------------------
    def section_exists(self, section_id: SectionId) -> bool:
        """Whether `section_id` exists at all, ignoring `as_of`.

        The get_filing_section TOOL needs this to tell an unknown id apart from
        one that simply had not been filed yet. Both are errors, but an agent
        that cannot tell them apart cannot decide whether to retry with a later
        as_of or to stop citing the section entirely.
        """
        return section_id in self._sections
