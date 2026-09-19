"""ResearchState - the single structured object the report is rendered from (ADR 0004).

Specified by docs/research-state.md.

Nothing downstream reads free-form agent text. Agents write Claims into the
section they own; the Report Generator renders those Claims deterministically.
That is what makes the verification gate meaningful: every sentence in the
finished report traces to a Claim, and every Claim traces to a fact or a filing
section.

Each section records its OWNING AGENT, which is also the retry routing key: when
the verifier fails a claim, the RetryDirective goes to the owner of the section
that claim lives in (docs/verification.md).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schema.contracts.analysis import Analysis
from schema.contracts.claims import Claim
from schema.contracts.common import (
    DataQuality,
    ISODate,
    ISOTimestamp,
    SchemaVersion,
    Ticker,
)
from schema.contracts.enums import AgentName, Mode, VerificationStatus
from schema.contracts.scenario_result import ScenarioResult
from schema.contracts.verification import VerificationResult

STATE_VERSION = "1.0.0"
"""Version of the ResearchState SHAPE. Bumped when sections are added or renamed,
independently of the contract-set SCHEMA_VERSION."""

SECTION_OWNERS: dict[str, AgentName] = {
    "company": AgentName.BUSINESS,
    "financials": AgentName.FINANCIAL,
    "balance_sheet": AgentName.FINANCIAL,
    "cash_flow": AgentName.FINANCIAL,
    "earnings_quality": AgentName.FINANCIAL,
    "management": AgentName.BUSINESS,
    "competitive_position": AgentName.BUSINESS,
    "valuation": AgentName.VALUATION,
    "expectations": AgentName.VALUATION,
    "catalysts": AgentName.BUSINESS,
    "risks": AgentName.RED_TEAM,
    "scenarios": AgentName.SCENARIO,
    "sp500_comparison": AgentName.SCENARIO,
    "decision": AgentName.SYNTHESIZER,
}
"""Canonical section -> owning agent map. The retry router reads this, so a
failed claim always has exactly one agent responsible for fixing it."""


class ResearchSection(BaseModel):
    """One section of the report, owned by exactly one agent."""

    model_config = ConfigDict(extra="allow")

    section_key: str = Field(min_length=1, description="Key from SECTION_OWNERS.")
    title: str = Field(min_length=1, description="Human-readable heading.")
    owner: AgentName = Field(description="The agent responsible; also the retry target.")
    claims: list[Claim] = Field(default_factory=list)
    verification_status: VerificationStatus = VerificationStatus.PENDING
    retry_count: int = Field(
        default=0, ge=0, description="Targeted retries spent on this section."
    )

    @model_validator(mode="after")
    def _check_owner_matches_canonical_map(self) -> ResearchSection:
        expected = SECTION_OWNERS.get(self.section_key)
        if expected is not None and self.owner is not expected:
            raise ValueError(
                f"section '{self.section_key}' is owned by {expected.value}, "
                f"not {self.owner.value}; retry routing depends on this"
            )
        return self

    @property
    def unverified_claims(self) -> list[Claim]:
        """Claims that will ship marked unverified if the retry cap is reached."""
        return [
            c
            for c in self.claims
            if c.verification_status
            in (VerificationStatus.FAILED, VerificationStatus.UNVERIFIED)
        ]


class ResearchSections(BaseModel):
    """The fourteen sections, in report order."""

    model_config = ConfigDict(extra="allow")

    company: ResearchSection
    financials: ResearchSection
    balance_sheet: ResearchSection
    cash_flow: ResearchSection
    earnings_quality: ResearchSection
    management: ResearchSection
    competitive_position: ResearchSection
    valuation: ResearchSection
    expectations: ResearchSection
    catalysts: ResearchSection
    risks: ResearchSection
    scenarios: ResearchSection
    sp500_comparison: ResearchSection
    decision: ResearchSection

    def as_list(self) -> list[ResearchSection]:
        """Sections in report order."""
        return [getattr(self, key) for key in SECTION_OWNERS]

    def by_owner(self, agent: AgentName) -> list[ResearchSection]:
        """Every section one agent is responsible for. Used by the retry router."""
        return [s for s in self.as_list() if s.owner is agent]

    @model_validator(mode="after")
    def _check_section_keys(self) -> ResearchSections:
        for key in SECTION_OWNERS:
            section = getattr(self, key)
            if section.section_key != key:
                raise ValueError(
                    f"field '{key}' holds a section keyed '{section.section_key}'"
                )
        return self


class ResearchState(BaseModel):
    """Everything known about one run. The report is a pure function of this object."""

    model_config = ConfigDict(extra="allow")

    state_version: str = Field(
        default=STATE_VERSION, description="Shape version of this object."
    )
    schema_version: SchemaVersion
    ticker: Ticker
    as_of: ISODate = Field(description="Point-in-time cutoff for the whole run (ADR 0003).")
    created_at: ISOTimestamp
    mode: Mode

    sections: ResearchSections
    agent_outputs: dict[AgentName, Analysis] = Field(
        default_factory=dict, description="Raw per-agent output, kept for the UI lanes."
    )
    scenario_result: ScenarioResult | None = Field(
        default=None, description="Set once calc.evaluate_scenarios has run."
    )
    verification: VerificationResult | None = Field(
        default=None, description="Set by audit.run_audit on the final pass."
    )
    data_quality: DataQuality

    redacted: bool = Field(
        default=False,
        description="True when a redact hook anonymized filing text before the agents "
        "saw it (backtest contamination, error A).",
    )

    @property
    def all_claims(self) -> list[Claim]:
        """Every claim across every section, in report order."""
        return [c for section in self.sections.as_list() for c in section.claims]

    @property
    def unverified_claims(self) -> list[Claim]:
        """Claims shipping marked unverified. Non-empty is allowed, never silent."""
        return [c for section in self.sections.as_list() for c in section.unverified_claims]

    @model_validator(mode="after")
    def _check_claim_ids_unique(self) -> ResearchState:
        seen: set[str] = set()
        for claim in self.all_claims:
            if claim.claim_id in seen:
                raise ValueError(f"duplicate claim_id across sections: {claim.claim_id}")
            seen.add(claim.claim_id)
        return self

    @model_validator(mode="after")
    def _check_backtest_is_point_in_time(self) -> ResearchState:
        if self.mode is Mode.BACKTEST and not self.as_of:
            raise ValueError("mode 'backtest' requires an as_of date")
        return self
