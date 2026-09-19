"""What the Synthesizer hands to the report (P3-owned shape, not a contract).

The Synthesizer writes the PROSE of the verdict card and answers the red team; it
emits no numbers (docs/pipeline.md). The Coordinator stores this on the
ResearchState as the extra field `synthesis`, so the report stays a pure function
of the state (ADR 0004). Every numeric field of the card comes from
`ResearchState.scenario_result` and the market snapshot instead.

This shape is additive and lives in an `extra="allow"` field of the state, so it
is not a contract change; if the team wants it promoted to schema/contracts/ that
needs a CONTRACT-CHANGE PR (see docs/requests/2026-09-19-p3-report-inputs.md).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RedTeamResponse(BaseModel):
    """The bear case as the Red Team argued it, and the Synthesizer's answer to it."""

    model_config = ConfigDict(extra="allow")

    summary: str = Field(min_length=1)
    responses_by_synthesizer: str = Field(min_length=1)
    drawdown_path: str | None = None
    requested_prior_shift: float | None = None


class Synthesis(BaseModel):
    """The prose half of the verdict card, plus the red-team exchange."""

    model_config = ConfigDict(extra="allow")

    thesis: str = Field(min_length=1, description="2-4 sentences.")
    primary_catalyst: str = Field(min_length=1)
    biggest_risk: str = Field(min_length=1)
    valuation: str = Field(description="cheap | reasonable | expensive | extremely_expensive")
    business_quality: str = Field(description="poor | average | good | excellent")
    financial_strength: str = Field(description="weak | average | strong | fortress")
    verdict: str = Field(description="strong_buy | buy | speculative_buy | hold | avoid | sell")
    ten_thousand_dollar_answer: dict = Field(
        description='{"choice": "this_stock"|"sp500", "reason": str}'
    )
    red_team: RedTeamResponse
