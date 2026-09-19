"""Retry routing: which agent has to fix which failure.

Specified by docs/verification.md "Retry routing table".

A failed claim lives in exactly one section, and every section has exactly one
owning agent (state.SECTION_OWNERS). So a failure always has one address, and
the retry re-runs that agent for that section rather than the whole pipeline.

Why targeted: a full rerun re-rolls agents that already passed, costs seven LLM
calls instead of one, and makes the run non-reproducible for no benefit.

Why capped at MAX_RETRIES: an agent that has failed the same check twice is not
going to pass on the third attempt, and a pipeline that retries forever has no
worst-case latency. After the cap the report SHIPS with those claims marked
unverified - visible and labelled, rather than blocked or quietly dropped
(ADR 0005).

TODO(roadmap Step 2, P2).
"""

from __future__ import annotations

from schema.contracts.enums import AgentName, IssueType
from schema.contracts.state import ResearchState
from schema.contracts.verification import RetryDirective, VerificationIssue

RETRYABLE: frozenset[IssueType] = frozenset(
    {
        IssueType.UNRESOLVED_FACT,
        IssueType.PROSE_NUMBER_MISMATCH,
        IssueType.SUPERSEDED_FACT,
        IssueType.ADJUSTED_AS_GAAP,
        IssueType.UNSUPPORTED_CLAIM,
        IssueType.CROSS_AGENT_CONTRADICTION,
    }
)
"""Issues an agent can plausibly fix by trying again with the failure explained."""

NOT_RETRYABLE: frozenset[IssueType] = frozenset(
    {IssueType.RECOMPUTE_MISMATCH, IssueType.FUTURE_FACT}
)
"""Issues retrying cannot fix.

RECOMPUTE_MISMATCH means calc/ and the stored value disagree - a code bug, not
an agent one. FUTURE_FACT means the data layer served something it should not
have. Both are escalated to a human rather than re-prompted.
"""


def owning_agent(state: ResearchState, issue: VerificationIssue) -> AgentName | None:
    """The agent responsible for the section this issue came from."""
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def build_directives(
    state: ResearchState, issues: list[VerificationIssue], attempt: int
) -> list[RetryDirective]:
    """Group retryable issues by section into one directive per section.

    One directive per section, not per issue: an agent redoing a section should
    see every problem with it at once.
    """
    raise NotImplementedError("TODO(roadmap Step 2, P2)")
