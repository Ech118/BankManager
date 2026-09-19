"""Verdict - what the reader actually sees. Rendered from ResearchState (ADR 0004).

Specified by docs/research-state.md. PRODUCED BY orchestrator.api.run_analysis
(the Report Generator). CONSUMED BY web/ and by audit/'s final consistency check.

Every number on the card comes from ScenarioResult or Metrics. The Synthesizer
writes the prose fields only; it never computes and never renders. The disclaimer
is required and non-empty, and a test asserts it is present (error M).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schema.contracts.analysis import Analysis
from schema.contracts.common import (
    DataQuality,
    Evidence,
    ISODate,
    ISOTimestamp,
    Probability,
    SchemaVersion,
    Ticker,
    ValueObject,
)
from schema.contracts.enums import AgentName, Mode, VerificationStatus
from schema.contracts.scenario_result import HorizonValues, ScenarioResult, Scores
from schema.contracts.verification import VerificationResult


class TenThousandDollarAnswer(BaseModel):
    """The plain-language question a reader actually has."""

    model_config = ConfigDict(extra="allow")

    choice: str = Field(description="this_stock | sp500")
    reason: str = Field(min_length=1, description="Written by the Synthesizer.")

    @model_validator(mode="after")
    def _check_choice(self) -> TenThousandDollarAnswer:
        if self.choice not in ("this_stock", "sp500"):
            raise ValueError(f"choice must be this_stock or sp500, got {self.choice!r}")
        return self


class VerdictCard(BaseModel):
    """The card shown first, before any section (error 7 in the original review)."""

    model_config = ConfigDict(extra="allow")

    company: str = Field(min_length=1)
    ticker: Ticker
    price: ValueObject
    market_cap: ValueObject

    thesis: str = Field(min_length=1, description="2-4 sentences, written by the Synthesizer.")
    scores: Scores = Field(description="From calc/'s rubric. The LLM never sets these.")

    p_beat_sp500_5y: Probability = Field(
        description="Equal to scenario_result.p_beat_sp500.long_term (3-5y)."
    )
    expected_5y_return: ValueObject = Field(description="Long-horizon expected return.")
    expected_return_vs_sp500: HorizonValues = Field(
        description="Expected return minus the index, at 0-12m, 1-3y and 3-5y."
    )

    primary_catalyst: str = Field(min_length=1)
    biggest_risk: str = Field(min_length=1)

    valuation: str = Field(description="cheap | reasonable | expensive | extremely_expensive")
    business_quality: str = Field(description="poor | average | good | excellent")
    financial_strength: str = Field(description="weak | average | strong | fortress")
    verdict: str = Field(
        description="strong_buy | buy | speculative_buy | hold | avoid | sell. "
        "Must agree with calc.validate_consistency."
    )
    ten_thousand_dollar_answer: TenThousandDollarAnswer

    @model_validator(mode="after")
    def _check_enums(self) -> VerdictCard:
        allowed = {
            "valuation": {"cheap", "reasonable", "expensive", "extremely_expensive"},
            "business_quality": {"poor", "average", "good", "excellent"},
            "financial_strength": {"weak", "average", "strong", "fortress"},
            "verdict": {"strong_buy", "buy", "speculative_buy", "hold", "avoid", "sell"},
        }
        for field, values in allowed.items():
            got = getattr(self, field)
            if got not in values:
                raise ValueError(f"{field} must be one of {sorted(values)}, got {got!r}")
        return self


class ReportSection(BaseModel):
    """One rendered section. `body_markdown` is GENERATED from Claims, never typed
    by an agent (ADR 0004)."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1, description="Matches a ResearchState section_key.")
    title: str = Field(min_length=1)
    body_markdown: str = Field(description="Rendered from the section's Claims.")
    agent: AgentName
    evidence: list[Evidence] = Field(default_factory=list)
    verification_status: VerificationStatus = VerificationStatus.PENDING
    unverified_claim_ids: list[str] = Field(
        default_factory=list,
        description="Claims that failed after the retry cap. Rendered as marked.",
    )


class RedTeamBlock(BaseModel):
    """The bear case, and the Synthesizer's obligation to answer it (error 5)."""

    model_config = ConfigDict(extra="allow")

    summary: str = Field(min_length=1, description="Strongest case against the leading view.")
    responses_by_synthesizer: str = Field(
        min_length=1, description="The Synthesizer MUST answer; an empty response is invalid."
    )
    drawdown_path: str | None = Field(
        default=None, description="The strongest 30%+ drawdown path, if one was argued."
    )
    requested_prior_shift: float | None = Field(
        default=None, description="Recorded in ScenarioResult.prior, applied within the cap."
    )


class Verdict(BaseModel):
    """The complete finished report object."""

    model_config = ConfigDict(extra="allow")

    schema_version: SchemaVersion
    ticker: Ticker
    as_of: ISODate
    generated_at: ISOTimestamp
    mode: Mode

    disclaimer: str = Field(
        min_length=20,
        description="REQUIRED and non-empty. Rendered on every page (error M).",
    )

    card: VerdictCard
    sections: list[ReportSection] = Field(min_length=1)
    red_team: RedTeamBlock
    agent_outputs: dict[AgentName, Analysis] = Field(default_factory=dict)

    scenario_result: ScenarioResult
    audit: VerificationResult
    data_quality: DataQuality

    metrics_ref: str | None = Field(
        default=None, description="Pointer to the Metrics object this was built from."
    )
    state_version: str | None = Field(
        default=None, description="ResearchState shape this was rendered from."
    )

    @model_validator(mode="after")
    def _check_card_matches_calc(self) -> Verdict:
        """The card may not disagree with calc/. This is the last line of defence."""
        sr = self.scenario_result
        if self.card.scores.model_dump() != sr.scores.model_dump():
            raise ValueError(
                "card.scores does not match scenario_result.scores; scores come from "
                "calc/'s rubric only"
            )
        if abs(self.card.p_beat_sp500_5y - sr.p_beat_sp500.long_term) > 1e-9:
            raise ValueError(
                f"card.p_beat_sp500_5y {self.card.p_beat_sp500_5y} does not match "
                f"scenario_result.p_beat_sp500.long_term {sr.p_beat_sp500.long_term}"
            )
        return self

    @model_validator(mode="after")
    def _check_ticker_consistent(self) -> Verdict:
        if self.card.ticker != self.ticker:
            raise ValueError(
                f"card.ticker {self.card.ticker} does not match verdict ticker {self.ticker}"
            )
        return self
