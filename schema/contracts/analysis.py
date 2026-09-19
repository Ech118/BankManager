"""Analysis - one P3 agent's structured output.

Specified by docs/pipeline.md. PRODUCED BY each agent in agents/.

A finding with empty evidence is INVALID and is dropped by the orchestrator
before it ever reaches audit/ (error I). That rule is enforced by the model, not
by a prompt, so a badly behaved LLM cannot smuggle an uncited claim through.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from schema.contracts.common import (
    Evidence,
    ISODate,
    SchemaVersion,
    Ticker,
    ValueObject,
)
from schema.contracts.enums import AgentName, Confidence, Trend


class Finding(BaseModel):
    """One assertion by an agent, with the evidence that makes it checkable."""

    model_config = ConfigDict(extra="allow")

    claim: str = Field(min_length=1)
    trend: Trend
    evidence: list[Evidence] = Field(
        min_length=1,
        description="At least one verbatim quote. Empty evidence makes the finding invalid.",
    )
    numbers: list[ValueObject] = Field(
        default_factory=list,
        description="Numbers cited by this finding. Never arithmetic done by the LLM.",
    )
    confidence: Confidence


class Analysis(BaseModel):
    """The full output of one agent pass."""

    model_config = ConfigDict(extra="allow")

    schema_version: SchemaVersion
    agent: AgentName
    ticker: Ticker
    as_of: ISODate
    model: str = Field(min_length=1, description="Model id used, or 'mock'.")
    summary: str = Field(min_length=1)
    findings: list[Finding] = Field(default_factory=list)
    tokens_in: int | None = Field(default=None, ge=0, description="Cost tracking (error K).")
    tokens_out: int | None = Field(default=None, ge=0)
