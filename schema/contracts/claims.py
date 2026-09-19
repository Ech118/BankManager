"""Claim - the unit an agent is allowed to assert (ADR 0002, ADR 0004).

Specified by docs/research-state.md.

Two rules make the verification gate possible, and both are enforced here rather
than left to a prompt:
  - A claim that carries a NUMBER must cite fact_ids. Agents never state a bare
    number; they point at a fact the truth layer already holds.
  - A qualitative claim must cite section_ids, so the verifier can string-match
    the quote against the filing text.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schema.contracts.common import (
    ClaimId,
    Evidence,
    FactId,
    SectionId,
    ValueObject,
)
from schema.contracts.enums import Confidence, DerivedBy, Trend, VerificationStatus

_NUMERIC_TOKEN = re.compile(r"\d[\d,]*(?:\.\d+)?")
"""Numerals in claim text. Spelled-out counts ("two large customers") are fine;
anything written as a numeral has to be traceable to something.

"Traceable" means one of exactly two things, and nothing else:
  - the claim cites fact_ids, so the number came from the truth layer; or
  - the numeral appears verbatim inside one of the claim's evidence quotes, so
    the verifier's string match already covers it (IssueType.UNSUPPORTED_CLAIM).
A numeral that satisfies neither is a bare number the agent invented.
"""


def _normalize_number(token: str) -> str:
    """Strip thousands separators so "1,200" in prose matches "1200" in a quote."""
    return token.replace(",", "")


class Claim(BaseModel):
    """One assertion made by an agent, or computed by code, inside a ResearchState section.

    The report is rendered from Claims, never from free-form agent prose (ADR 0004).
    """

    model_config = ConfigDict(extra="allow")

    claim_id: ClaimId
    text: str = Field(min_length=1, description="The assertion, as one sentence.")

    value: ValueObject | None = Field(
        default=None,
        description="The number this claim is about, when it is about a number.",
    )
    fact_ids: list[FactId] = Field(
        default_factory=list,
        description="Facts this claim rests on. REQUIRED whenever a number appears.",
    )
    section_ids: list[SectionId] = Field(
        default_factory=list,
        description="Filing sections this claim rests on. REQUIRED for qualitative claims.",
    )
    evidence: list[Evidence] = Field(
        default_factory=list,
        description="Verbatim quotes. The verifier string-matches each one.",
    )

    derived_by: DerivedBy = Field(
        description="code = computed in calc/, agent = asserted by an LLM, "
        "filing_text = lifted from a filing."
    )
    trend: Trend = Trend.NEUTRAL
    confidence: Confidence = Confidence.MEDIUM
    verification_status: VerificationStatus = VerificationStatus.PENDING

    @property
    def prose_numbers(self) -> list[str]:
        """Numerals written into the claim text, normalized."""
        return [_normalize_number(t) for t in _NUMERIC_TOKEN.findall(self.text)]

    @property
    def has_number(self) -> bool:
        """True when this claim asserts a number, in its value or in its prose."""
        return self.value is not None or bool(self.prose_numbers)

    @property
    def unsourced_numbers(self) -> list[str]:
        """Numerals backed by neither a fact_id nor an evidence quote."""
        if self.fact_ids:
            return []
        quoted = " ".join(_normalize_number(e.quote) for e in self.evidence)
        return [n for n in self.prose_numbers if n not in quoted]

    @model_validator(mode="after")
    def _check_numbers_cite_facts(self) -> Claim:
        """No bare numbers. Every numeral traces to a fact or to a quoted source."""
        if self.value is not None and not self.fact_ids:
            raise ValueError(
                f"{self.claim_id}: a claim carrying a value must cite at least one "
                "fact_id (principle 2: agents cite fact_ids, never bare numbers)"
            )
        unsourced = self.unsourced_numbers
        if unsourced:
            raise ValueError(
                f"{self.claim_id}: claim text contains number(s) {unsourced} that cite "
                f"no fact_ids and appear in no evidence quote: {self.text!r}"
            )
        return self

    @model_validator(mode="after")
    def _check_qualitative_cites_sections(self) -> Claim:
        """A qualitative agent claim must be checkable against filing text."""
        if (
            self.derived_by is DerivedBy.AGENT
            and not self.has_number
            and not self.section_ids
            and not self.evidence
        ):
            raise ValueError(
                f"{self.claim_id}: a qualitative agent claim must cite section_ids or "
                "evidence so the verifier can check it"
            )
        return self

    @model_validator(mode="after")
    def _check_evidence_sections_are_cited(self) -> Claim:
        """Evidence must point at something; keeps UNSUPPORTED_CLAIM checkable."""
        for ev in self.evidence:
            if not ev.source_id:
                raise ValueError(f"{self.claim_id}: evidence without a source_id")
        return self
