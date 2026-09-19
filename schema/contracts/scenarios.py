"""Scenarios - the P3 Valuation/Scenario Agent's PROPOSAL. Inputs only.

Specified by docs/pipeline.md. PRODUCED BY the Scenario Agent.
CONSUMED BY calc.api.evaluate_scenarios.

The LLM proposes scenario inputs and weights, each with a written rationale. It
never produces P(beat S&P), never produces a score, and never gets the last word
on a weight: calc/ bounds every weight within a configured band around the
defaults, and bounds the prior shift within a hard cap (ADR 0001, error C).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schema.contracts.common import (
    Evidence,
    ISODate,
    Probability,
    SchemaVersion,
    Ticker,
    ValueObject,
)
from schema.contracts.enums import AgentName, ScenarioName


class Scenario(BaseModel):
    """One of bear / base / bull.

    `probability` is a REQUEST, not a decision. calc/ clamps it into the
    configured band and records the clamp in ScenarioResult.weights.
    """

    model_config = ConfigDict(extra="allow")

    probability: Probability = Field(
        description="REQUESTED weight in [0,1]. calc/ bounds it before use."
    )
    probability_rationale: str = Field(
        default="",
        description="Why this weight. Required by the prompt; audited by the verifier.",
    )
    horizon_years: int = Field(ge=1, le=10)
    revenue_cagr: ValueObject
    terminal_margin: ValueObject = Field(description="Net margin at the horizon.")
    eps_at_horizon: ValueObject
    exit_multiple: ValueObject = Field(description="P/E at the horizon.")
    rationale: str = Field(min_length=1)
    evidence: list[Evidence] = Field(default_factory=list)


class PriorShift(BaseModel):
    """A requested tilt to the base-rate prior for P(beat S&P).

    Both the Scenario Agent and the Red Team may request one. calc/ applies the
    sum only within a hard cap and records requested vs applied (error C).
    """

    model_config = ConfigDict(extra="allow")

    value: float = Field(
        ge=-1.0, le=1.0, description="Requested shift. Negative argues the stock lags."
    )
    reason: str = Field(min_length=1, description="Why. An unjustified shift is rejected.")
    source: AgentName = Field(
        default=AgentName.SCENARIO, description="Which agent asked for it."
    )


class Scenarios(BaseModel):
    """The complete proposal handed to calc.api.evaluate_scenarios."""

    model_config = ConfigDict(extra="allow")

    schema_version: SchemaVersion
    ticker: Ticker
    as_of: ISODate
    scenarios: dict[ScenarioName, Scenario] = Field(
        description="Exactly bear, base and bull."
    )
    prior_shift: PriorShift

    @model_validator(mode="after")
    def _check_all_three_scenarios(self) -> Scenarios:
        missing = set(ScenarioName) - set(self.scenarios)
        if missing:
            raise ValueError(
                f"scenarios must contain bear, base and bull; missing {sorted(m.value for m in missing)}"
            )
        return self

    @model_validator(mode="after")
    def _check_probabilities_sum_to_one(self) -> Scenarios:
        """Requested weights must be a distribution before calc/ bounds them."""
        total = sum(s.probability for s in self.scenarios.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"scenario probabilities must sum to 1.0, got {total}")
        return self
