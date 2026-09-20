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

"""

from __future__ import annotations

import re

from schema.contracts.enums import AgentName, IssueType
from schema.contracts.state import ResearchState
from schema.contracts.verification import MAX_RETRIES, RetryDirective, VerificationIssue

_SECTION_KEY_RE = re.compile(r"^sections\.([A-Za-z0-9_]+)")

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


def section_key_of(issue: VerificationIssue) -> str | None:
    m = _SECTION_KEY_RE.match(issue.path)
    return m.group(1) if m else None


def owning_agent(state: ResearchState, issue: VerificationIssue) -> AgentName | None:
    """The agent responsible for the section this issue came from."""
    key = section_key_of(issue)
    if key is None:
        return None
    section = getattr(state.sections, key, None)
    return section.owner if section else None


def build_directives(
    state: ResearchState, issues: list[VerificationIssue], attempt: int
) -> list[RetryDirective]:
    """Group retryable issues by section into one directive per section.

    One directive per section, not per issue: an agent redoing a section should
    see every problem with it at once. Skips any section that has already
    reached MAX_RETRIES - the section's own retry_count is the source of truth
    for the cap, `attempt` is only stamped onto the directive for logging/the
    retry prompt (docs/requests/2026-09-19-p3-to-p2-verifier-and-retry-contract.md).
    """
    by_section: dict[str, list[VerificationIssue]] = {}
    for issue in issues:
        if issue.issue_type not in RETRYABLE:
            continue
        key = section_key_of(issue)
        if key is None:
            continue
        by_section.setdefault(key, []).append(issue)

    directives = []
    for key, section_issues in by_section.items():
        section = getattr(state.sections, key, None)
        if section is None or section.retry_count >= MAX_RETRIES:
            continue
        directives.append(RetryDirective(
            target_agent=section.owner,
            section_key=key,
            issues=section_issues,
            attempt=attempt,
            max_attempts=MAX_RETRIES,
        ))
    return directives
