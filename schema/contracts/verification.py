"""Verification contracts - the gate between the agents and the reader (ADR 0005).

Specified by docs/verification.md. PRODUCED BY audit.api.run_audit.

The gate is mostly deterministic code. Only one issue type (UNSUPPORTED_CLAIM)
needs an LLM, and that LLM is injected as a callable so audit/ depends on no
model SDK. When a check fails, the RetryDirective targets the ONE agent that owns
the section the claim lives in; after the cap, the report ships with the failing
claims marked unverified rather than being blocked.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schema.contracts.common import ClaimId, FactId, SchemaVersion, SectionId
from schema.contracts.enums import (
    LLM_ISSUE_TYPES,
    AgentName,
    IssueType,
    Severity,
    VerificationStatus,
)

MAX_RETRIES = 2
"""Targeted retries per section before its claims ship marked unverified."""


class VerificationIssue(BaseModel):
    """One failed check, with enough detail to route a retry and to show the reader."""

    model_config = ConfigDict(extra="allow")

    issue_type: IssueType
    severity: Severity
    path: str = Field(
        min_length=1, description="Dotted path into the audited object, e.g. sections.valuation."
    )
    message: str = Field(min_length=1, description="What is wrong, in one sentence.")

    claim_id: ClaimId | None = None
    fact_id: FactId | None = None
    section_id: SectionId | None = None

    expected: str | None = Field(default=None, description="What the check computed.")
    actual: str | None = Field(default=None, description="What the claim asserted.")

    checked_by_llm: bool = Field(
        default=False, description="True only for the qualitative-claim check."
    )

    @model_validator(mode="after")
    def _check_llm_flag_matches_type(self) -> VerificationIssue:
        """Only UNSUPPORTED_CLAIM may be produced by an LLM (ADR 0005)."""
        if self.checked_by_llm and self.issue_type not in LLM_ISSUE_TYPES:
            raise ValueError(
                f"{self.issue_type.value} is a deterministic check and must not be "
                "attributed to an LLM"
            )
        return self

    @model_validator(mode="after")
    def _check_recompute_shows_its_work(self) -> VerificationIssue:
        """A mismatch claim is only actionable if it names both numbers."""
        needs_both = {IssueType.RECOMPUTE_MISMATCH, IssueType.PROSE_NUMBER_MISMATCH}
        if self.issue_type in needs_both and (self.expected is None or self.actual is None):
            raise ValueError(
                f"{self.issue_type.value} must record both expected and actual"
            )
        return self


class RetryDirective(BaseModel):
    """An instruction to re-run ONE agent for ONE section, with the reasons.

    Targeted, not a whole-pipeline rerun: re-running everything would re-roll
    agents that already passed and would make cost unpredictable (error K).
    """

    model_config = ConfigDict(extra="allow")

    target_agent: AgentName
    section_key: str = Field(min_length=1, description="The section to redo.")
    issues: list[VerificationIssue] = Field(
        min_length=1, description="Why. Passed back into the agent's prompt."
    )
    attempt: int = Field(ge=1, description="1-based attempt number.")
    max_attempts: int = Field(default=MAX_RETRIES, ge=1)

    @model_validator(mode="after")
    def _check_attempt_within_cap(self) -> RetryDirective:
        if self.attempt > self.max_attempts:
            raise ValueError(
                f"attempt {self.attempt} exceeds max_attempts {self.max_attempts}; "
                "the caller should have marked the claims unverified instead"
            )
        return self


class VerificationResult(BaseModel):
    """The audit report. `passed` is false if any issue has severity 'error'."""

    model_config = ConfigDict(extra="allow")

    schema_version: SchemaVersion
    passed: bool
    issues: list[VerificationIssue] = Field(default_factory=list)

    claims_checked: int = Field(default=0, ge=0)
    claims_verified: int = Field(default=0, ge=0)
    claims_unverified: int = Field(
        default=0, ge=0, description="Shipped marked unverified after the retry cap."
    )

    llm_checks_run: int = Field(
        default=0, ge=0, description="Cost tracking; keep this number small."
    )
    retries_issued: list[RetryDirective] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_passed_matches_issues(self) -> VerificationResult:
        has_error = any(i.severity is Severity.ERROR for i in self.issues)
        if self.passed and has_error:
            raise ValueError(
                "passed=True but at least one issue has severity 'error'"
            )
        if not self.passed and not has_error:
            raise ValueError(
                "passed=False but no issue has severity 'error'; a failure must say why"
            )
        return self

    @model_validator(mode="after")
    def _check_claim_counts(self) -> VerificationResult:
        total = self.claims_verified + self.claims_unverified
        if total > self.claims_checked:
            raise ValueError(
                f"claims_verified + claims_unverified ({total}) exceeds "
                f"claims_checked ({self.claims_checked})"
            )
        return self

    def status_for(self, claim_id: str) -> VerificationStatus:
        """Terminal status of one claim, given this result."""
        if any(i.claim_id == claim_id for i in self.issues):
            return VerificationStatus.FAILED
        return VerificationStatus.VERIFIED
