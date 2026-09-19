"""FinancialFact - the row type of the financial truth layer (ADR 0002).

Specified by docs/data-model.md. P1 produces these from XBRL and filing text; P2
produces DERIVED ones with lineage; P3 never constructs one, it cites fact_ids.

Provenance is mandatory. There is no way to build a FinancialFact that cannot be
traced back to a filing, an API response, or an explicit derivation.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schema.contracts.common import (
    FRACTION_SANITY_LIMIT,
    FactId,
    ISODate,
    ISOTimestamp,
    Period,
    SectionId,
    Ticker,
)
from schema.contracts.enums import FilingType, PeriodType, SourceKind, Unit


class Derivation(BaseModel):
    """How a derived fact was computed. Required when source_kind is `derived`.

    `formula` is a human-readable expression over the input metric names, e.g.
    "op_cash_flow - capex". The verifier recomputes it and raises
    IssueType.RECOMPUTE_MISMATCH when the stored value disagrees.
    """

    model_config = ConfigDict(extra="allow")

    formula: str = Field(
        min_length=1, description='Expression over input metrics, e.g. "op_cash_flow - capex".'
    )
    input_fact_ids: list[FactId] = Field(
        min_length=1, description="Every fact this value was computed from."
    )
    computed_by: str = Field(
        default="calc",
        description="Module that computed it. calc/ is the only legitimate producer.",
    )


class FinancialFact(BaseModel):
    """One number, at one period, from one filing, with full provenance.

    `value` is ALWAYS in full units (docs/data-model.md, decision 9). `scale` is
    provenance only: it records what the filing reported ("millions") and must
    never be applied again by a consumer.
    """

    model_config = ConfigDict(extra="allow")

    fact_id: FactId
    company_id: Ticker = Field(description="Ticker. CIK lives on CompanyProfile.")
    metric: str = Field(
        min_length=1,
        description="Canonical metric name, e.g. revenue, op_cash_flow. Not the XBRL tag.",
    )
    xbrl_concept: str | None = Field(
        default=None,
        description="The us-gaap tag actually used, recorded because tags vary by filer.",
    )

    value: float | None = Field(description="Full units. Null only for an unavailable fact.")
    unit: Unit
    currency: str | None = Field(
        default="USD", description="ISO 4217 code for monetary units; null otherwise."
    )
    scale: str | None = Field(
        default=None,
        description='What the filing reported ("units"/"thousands"/"millions"). '
        "PROVENANCE ONLY - value is already normalized.",
    )

    period_type: PeriodType
    period_start: ISODate | None = Field(
        default=None, description="Required for duration facts; must be null for instant."
    )
    period_end: ISODate
    fiscal_period: Period

    dimension: dict[str, str] | None = Field(
        default=None,
        description="XBRL segment axis members. None means the CONSOLIDATED total "
        "(docs/sec-pitfalls.md: never sum dimensioned facts into a total).",
    )

    filing_type: FilingType | None = None
    accession_number: str | None = Field(
        default=None, description="Required for anything sourced from a filing."
    )
    filed_at: ISODate | None = Field(
        default=None,
        description="Filing date. Point-in-time queries drop facts filed after as_of.",
    )
    retrieved_at: ISOTimestamp = Field(description="When we fetched it. Always required.")

    source_url: str | None = None
    source_location: SectionId | str | None = Field(
        default=None, description="Section id or XBRL fragment the value was read from."
    )
    source_kind: SourceKind

    derivation: Derivation | None = Field(
        default=None, description="Required if and only if source_kind is `derived`."
    )
    superseded_by: FactId | None = Field(
        default=None,
        description="Set when a later filing restated this value. Citing a superseded "
        "fact raises IssueType.SUPERSEDED_FACT.",
    )

    @model_validator(mode="after")
    def _check_derivation_matches_kind(self) -> FinancialFact:
        """A derived fact REQUIRES a derivation; nothing else may carry one."""
        if self.source_kind is SourceKind.DERIVED and self.derivation is None:
            raise ValueError(
                f"{self.fact_id}: source_kind 'derived' requires a derivation "
                "(formula + input_fact_ids)"
            )
        if self.source_kind is not SourceKind.DERIVED and self.derivation is not None:
            raise ValueError(
                f"{self.fact_id}: only source_kind 'derived' may carry a derivation, "
                f"got {self.source_kind.value}"
            )
        return self

    @model_validator(mode="after")
    def _check_provenance_present(self) -> FinancialFact:
        """Every fact must be traceable. Which field is required depends on the kind."""
        kind = self.source_kind
        if kind in (SourceKind.XBRL_REPORTED, SourceKind.FILING_TEXT):
            if not self.accession_number:
                raise ValueError(
                    f"{self.fact_id}: source_kind '{kind.value}' requires an accession_number"
                )
            if not self.filed_at:
                raise ValueError(
                    f"{self.fact_id}: source_kind '{kind.value}' requires filed_at "
                    "so point-in-time queries can exclude it"
                )
        elif kind is SourceKind.MARKET_API:
            if not self.source_url and not self.source_location:
                raise ValueError(
                    f"{self.fact_id}: source_kind 'market_api' requires a source_url "
                    "or source_location"
                )
        elif kind is SourceKind.ESTIMATE:
            if not self.source_url and not self.source_location:
                raise ValueError(
                    f"{self.fact_id}: source_kind 'estimate' requires a source_url "
                    "or source_location naming who estimated it"
                )
        return self

    @model_validator(mode="after")
    def _check_period_shape(self) -> FinancialFact:
        """duration facts span a range; instant facts are a single point."""
        if self.period_type is PeriodType.DURATION and not self.period_start:
            raise ValueError(f"{self.fact_id}: duration facts require a period_start")
        if self.period_type is PeriodType.INSTANT and self.period_start is not None:
            raise ValueError(
                f"{self.fact_id}: instant facts must not have a period_start, "
                f"got {self.period_start}"
            )
        if self.period_start and self.period_start > self.period_end:
            raise ValueError(
                f"{self.fact_id}: period_start {self.period_start} is after "
                f"period_end {self.period_end}"
            )
        return self

    @model_validator(mode="after")
    def _check_fraction_is_not_percent(self) -> FinancialFact:
        """Same fractions-not-percents rule the ValueObject enforces."""
        if (
            self.unit is Unit.FRACTION
            and self.value is not None
            and abs(self.value) > FRACTION_SANITY_LIMIT
        ):
            raise ValueError(
                f"{self.fact_id}: unit 'fraction' value {self.value} looks like a "
                "percent; use fractions (0.25 = 25%)"
            )
        return self

    @model_validator(mode="after")
    def _check_not_self_superseding(self) -> FinancialFact:
        if self.superseded_by is not None and self.superseded_by == self.fact_id:
            raise ValueError(f"{self.fact_id}: a fact cannot supersede itself")
        return self

    @property
    def is_current(self) -> bool:
        """False once a later filing restated this value."""
        return self.superseded_by is None
