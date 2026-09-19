"""Filing and FilingSection - filings parsed by STRUCTURE, never chunk-and-embed.

Specified by docs/data-model.md and ADR 0006. P1 splits each 10-K/10-Q into
canonical Items and notes, keeps character offsets into the original document,
and serves the text verbatim. Nothing in this layer summarises.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schema.contracts.common import (
    ISODate,
    ISOTimestamp,
    Period,
    SectionId,
    SourceId,
    Ticker,
)
from schema.contracts.enums import FilingType, ItemCode


class Filing(BaseModel):
    """One SEC submission. `filed_at` is what every point-in-time query filters on."""

    model_config = ConfigDict(extra="allow")

    accession: str = Field(min_length=1, description="SEC accession number, dashed form.")
    company_id: Ticker
    cik: str | None = None
    form: FilingType
    fiscal_period: Period
    period_end: ISODate
    filed_at: ISODate = Field(
        description="Filing date. A run with as_of=D must not see filings after D."
    )
    retrieved_at: ISOTimestamp
    source_url: str | None = None
    section_ids: list[SectionId] = Field(
        default_factory=list, description="Sections parsed out of this filing."
    )


class FilingSection(BaseModel):
    """One structural chunk of a filing: an Item, or a note within the financials.

    `text` is plain text with HTML stripped, returned as filed. Agents receive it
    wrapped as DATA - never as instructions (prompt-injection rule, ADR 0005).
    """

    model_config = ConfigDict(extra="allow")

    section_id: SectionId = Field(description="Repository key, e.g. sec:<accession>:mdna.")
    source_id: SourceId = Field(
        description="Citation key used by Evidence, e.g. src:edgar:<accession>:mdna. "
        "Evidence cites this; the repository is keyed on section_id."
    )
    accession: str = Field(min_length=1)
    company_id: Ticker
    form: FilingType
    fiscal_period: Period
    filed_at: ISODate
    item: ItemCode = Field(description="Canonical section name, not the filer's heading.")
    heading_path: list[str] = Field(
        default_factory=list,
        description='Headings from document root down, e.g. ["Part I", "Item 1. Business"].',
    )
    char_start: int = Field(ge=0, description="Offset into the source document.")
    char_end: int = Field(ge=0)
    char_count: int = Field(ge=0)
    text: str = Field(default="", description="Verbatim plain text. Never summarised.")

    @model_validator(mode="after")
    def _check_offsets(self) -> FilingSection:
        if self.char_end < self.char_start:
            raise ValueError(
                f"{self.section_id}: char_end {self.char_end} precedes "
                f"char_start {self.char_start}"
            )
        expected = self.char_end - self.char_start
        if self.char_count != expected:
            raise ValueError(
                f"{self.section_id}: char_count {self.char_count} does not match "
                f"char_end - char_start ({expected})"
            )
        if self.text and len(self.text) != self.char_count:
            raise ValueError(
                f"{self.section_id}: text length {len(self.text)} does not match "
                f"char_count {self.char_count}"
            )
        return self
