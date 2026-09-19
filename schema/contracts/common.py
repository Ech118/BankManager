"""Shared building blocks: constrained id types, the ValueObject, evidence, scope.

Specified by docs/data-model.md.

ValueObject carries the four conditional rules that used to live as JSON Schema
`if`/`then` logic in the hand-written schema/common.json. They are now enforced in
THREE places, and all three are tested:
  1. `ValueObject` model validators (runtime, every partition),
  2. the exported JSON Schema (via __get_pydantic_json_schema__ below, so
     non-Python consumers such as web/ keep the same guarantees),
  3. tests/contracts/test_value_rules.py.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    GetJsonSchemaHandler,
    StringConstraints,
    model_validator,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from schema.contracts.enums import Unit, ValueStatus, ValueType

# --------------------------------------------------------------------------
# Constrained primitives. Patterns match the v1.0.0 contract exactly.
# --------------------------------------------------------------------------

SchemaVersion = Annotated[str, StringConstraints(pattern=r"^\d+\.\d+\.\d+$")]
"""Semantic version of the contract set, e.g. "2.0.0"."""

Ticker = Annotated[str, StringConstraints(pattern=r"^[A-Z]{1,5}([.-][A-Z])?$")]
"""Uppercase ticker. Share classes use . or - (e.g. BRK.B). Also the input allow-list."""

ISODate = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$")]
"""ISO 8601 calendar date, YYYY-MM-DD."""

ISOTimestamp = Annotated[
    str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
]
"""UTC ISO 8601 timestamp, e.g. 2026-09-19T12:00:00Z."""

Period = Annotated[str, StringConstraints(pattern=r"^(FY\d{4}|Q[1-4]-\d{4})$")]
"""Fiscal period label: FY2025 (annual) or Q2-2026 (quarter)."""

SourceId = Annotated[str, StringConstraints(pattern=r"^src:[a-z0-9_]+:[A-Za-z0-9._:-]+$")]
"""Stable pointer into Factsheet.sources, e.g. src:edgar:0001234567-26-000010:xbrl.

Two prefixes are legal outside the fact sheet: src:llm:<agent> for an
LLM-proposed assumption, and src:config:<name> for a calc/ constant.
"""

FactId = Annotated[str, StringConstraints(pattern=r"^fact:[A-Za-z0-9._:-]+$")]
"""Identity of one FinancialFact row, e.g. fact:ACME:revenue:FY2025."""

SectionId = Annotated[str, StringConstraints(pattern=r"^sec:[A-Za-z0-9._:-]+$")]
"""Identity of one FilingSection, e.g. sec:0001234567-26-000010:mdna."""

ClaimId = Annotated[str, StringConstraints(pattern=r"^claim:[A-Za-z0-9._:-]+$")]
"""Identity of one Claim, e.g. claim:financial:fcf-conversion."""

Probability = Annotated[float, Field(ge=0.0, le=1.0)]
"""Bare probability in [0,1]. A documented exception to the ValueObject rule."""

Score = Annotated[int, Field(ge=1, le=10)]
"""Integer buyability score 1..10. A documented exception to the ValueObject rule."""

FRACTION_SANITY_LIMIT = 10.0
"""|value| for unit=fraction. 0.25 means 25%; 25 would be a percent slipping through."""

_VALUE_OBJECT_JSON_RULES: list[dict[str, Any]] = [
    {
        "title": "status ok requires a numeric value",
        "if": {"properties": {"status": {"const": "ok"}}, "required": ["status"]},
        "then": {"required": ["value"], "properties": {"value": {"type": "number"}}},
    },
    {
        "title": "status ok requires a source_id or a non-empty derived_from",
        "if": {"properties": {"status": {"const": "ok"}}, "required": ["status"]},
        "then": {
            "anyOf": [
                {"properties": {"source_id": {"type": "string"}}, "required": ["source_id"]},
                {
                    "required": ["derived_from"],
                    "properties": {"derived_from": {"type": "array", "minItems": 1}},
                },
            ]
        },
    },
    {
        "title": "status unavailable requires a null value",
        "if": {
            "properties": {"status": {"const": "unavailable"}},
            "required": ["status"],
        },
        "then": {"properties": {"value": {"type": "null"}}},
    },
    {
        "title": "fractions are fractions, not percents",
        "if": {"properties": {"unit": {"const": "fraction"}}, "required": ["unit"]},
        "then": {
            "properties": {
                "value": {
                    "anyOf": [
                        {
                            "type": "number",
                            "minimum": -FRACTION_SANITY_LIMIT,
                            "maximum": FRACTION_SANITY_LIMIT,
                        },
                        {"type": "null"},
                    ]
                }
            }
        },
    },
]
"""The conditional rules, kept in the exported JSON Schema so web/ sees them too."""


class ValueObject(BaseModel):
    """Every reported or computed financial number in the system.

    Fractions, not percents. Money in full USD. Missing data is
    {"value": null, "status": "unavailable"} - never 0, never "N/A", never an
    omitted key.

    A value computed in code from facts has type "fact" and lists `derived_from`.
    Discount rate, terminal growth and exit multiples are "assumption".
    Consensus numbers and scenario outputs are "estimate".
    """

    model_config = ConfigDict(extra="allow")

    value: float | None = Field(
        description="The number in full units, or null when status is unavailable."
    )
    unit: Unit
    type: ValueType
    status: ValueStatus
    source_id: SourceId | None = Field(
        default=None,
        description="Where the number came from. Required unless derived_from is set.",
    )
    derived_from: list[str] = Field(
        default_factory=list,
        description="Dotted paths or fact_ids this value was computed from.",
    )

    @model_validator(mode="after")
    def _check_status_ok_has_number(self) -> ValueObject:
        """Rule 1: status ok requires a numeric value."""
        if self.status is ValueStatus.OK and self.value is None:
            raise ValueError("status 'ok' requires a numeric value, got null")
        return self

    @model_validator(mode="after")
    def _check_status_ok_has_provenance(self) -> ValueObject:
        """Rule 2: status ok requires a source_id or a non-empty derived_from."""
        if self.status is ValueStatus.OK and not self.source_id and not self.derived_from:
            raise ValueError(
                "status 'ok' requires either a source_id or a non-empty derived_from"
            )
        return self

    @model_validator(mode="after")
    def _check_unavailable_is_null(self) -> ValueObject:
        """Rule 3: status unavailable requires a null value (never 0)."""
        if self.status is ValueStatus.UNAVAILABLE and self.value is not None:
            raise ValueError(
                f"status 'unavailable' requires value null, got {self.value!r}"
            )
        return self

    @model_validator(mode="after")
    def _check_fraction_is_not_percent(self) -> ValueObject:
        """Rule 4: a fraction of 25 is a percent that escaped conversion."""
        if (
            self.unit is Unit.FRACTION
            and self.value is not None
            and abs(self.value) > FRACTION_SANITY_LIMIT
        ):
            raise ValueError(
                f"unit 'fraction' value {self.value} looks like a percent; "
                "use fractions (0.25 = 25%)"
            )
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        """Re-attach the conditional rules to the exported JSON Schema.

        pydantic cannot infer if/then from a model_validator, so without this the
        generated schema/*.json would be WEAKER than the v1.0.0 hand-written one.
        """
        schema = handler.resolve_ref_schema(handler(core_schema))
        schema["allOf"] = [dict(rule) for rule in _VALUE_OBJECT_JSON_RULES]
        return schema


class Evidence(BaseModel):
    """A verbatim quote from a source, string-matched by the verifier.

    The quote must appear in the text behind `source_id` after whitespace
    normalization, or audit/ raises IssueType.UNSUPPORTED_CLAIM.
    """

    model_config = ConfigDict(extra="allow")

    quote: str = Field(min_length=8, description="Verbatim text, copied not paraphrased.")
    source_id: SourceId


class SourceRef(BaseModel):
    """Registry entry describing where one source_id came from."""

    model_config = ConfigDict(extra="allow")

    kind: str = Field(
        description="edgar_xbrl | edgar_text | market | fred | news | config | mock"
    )
    url: str | None = None
    accession: str | None = None
    fetched_at: ISOTimestamp


class DataQuality(BaseModel):
    """Run-level data health, surfaced as a banner in the report (error E)."""

    model_config = ConfigDict(extra="allow")

    overall: str = Field(description="ok | partial | degraded")
    gaps: list[str] = Field(
        default_factory=list, description="Human-readable description of each gap."
    )


class Scope(BaseModel):
    """Result of data.api.check_scope. v1 covers non-financial operating companies."""

    model_config = ConfigDict(extra="allow")

    in_scope: bool
    reason: str | None = Field(
        default=None, description="Why the ticker was rejected; null when in scope."
    )
