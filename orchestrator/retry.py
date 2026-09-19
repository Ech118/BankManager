"""Targeted retry execution. Specified by docs/verification.md.

audit/routing.py (P2) decides WHICH agent gets a retry and returns the directives in
`VerificationResult.retries_issued`; this module runs them.

The rule: re-run one agent for one section, with the failures explained in the prompt, at most
twice. Not the whole pipeline - a full rerun re-rolls agents that already passed, costs seven LLM
calls instead of one, and makes the run non-reproducible for no benefit (error K).

After the cap the claims ship marked `unverified`. That is the deliberate choice: a report with
two labelled unverified claims is more useful, and more honest, than no report (ADR 0005).

Nothing here ever hides a failed claim. A retry that produces no replacement claims for a section
leaves the original claims in place, still failing, to be marked unverified.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from schema.contracts.claims import Claim
from schema.contracts.enums import AgentName, Severity, VerificationStatus
from schema.contracts.state import ResearchState
from schema.contracts.verification import (
    MAX_RETRIES,
    RetryDirective,
    VerificationIssue,
    VerificationResult,
)

log = logging.getLogger("bankmanager.retry")

MAX_ATTEMPTS = MAX_RETRIES
"""Two attempts per section (schema.contracts.verification.MAX_RETRIES)."""

Rerun = Callable[[AgentName, list[str], str], list[Claim]]
"""(agent, feedback lines, claim-id prefix) -> the agent's fresh claims. Supplied by the Coordinator."""


def directive_feedback(state: ResearchState, directive: RetryDirective) -> list[str]:
    """Explain every problem with the section at once, naming the failing claim's own words."""
    section = getattr(state.sections, directive.section_key)
    text_by_id = {c.claim_id: c.text for c in section.claims}
    lines = [
        f"Redo the `{directive.section_key}` section (attempt {directive.attempt} of {directive.max_attempts})."
    ]
    for issue in directive.issues:
        parts = [f"[{issue.issue_type.value}] {issue.message}"]
        if issue.claim_id in text_by_id:
            parts.append(f'claim: "{text_by_id[issue.claim_id]}"')
        if issue.expected is not None:
            parts.append(f"expected: {issue.expected}")
        if issue.actual is not None:
            parts.append(f"you wrote: {issue.actual}")
        lines.append("; ".join(parts))
    return lines


def apply_directive(state: ResearchState, directive: RetryDirective, rerun: Rerun) -> ResearchState:
    """Re-run one agent for one section with the issues fed back into its prompt.

    Only the claims for `directive.section_key` are replaced; the agent's other sections, and every
    other agent's claims, are untouched. Replacement claims get a per-attempt id prefix so ids stay
    unique across the state.
    """
    section = getattr(state.sections, directive.section_key)
    fresh = rerun(
        directive.target_agent, directive_feedback(state, directive), f"r{directive.attempt}-"
    )
    replacements = [
        c for c in fresh if (c.model_extra or {}).get("section_key") == directive.section_key
    ]
    section.retry_count += 1
    if not replacements:
        log.warning(
            "retry of %s produced no claims for %s; keeping the originals",
            directive.target_agent.value,
            directive.section_key,
        )
        return state
    for claim in replacements:
        claim.verification_status = VerificationStatus.PENDING
    section.claims = replacements
    section.verification_status = VerificationStatus.PENDING
    return state


def failing_claim_ids(result: VerificationResult) -> set[str]:
    return {i.claim_id for i in result.issues if i.claim_id and i.severity is Severity.ERROR}


def mark_unverified(state: ResearchState, result: VerificationResult) -> ResearchState:
    """Mark claims that failed after the cap, so the report can label them.

    The report renders these visibly. A claim that quietly disappeared would leave the reader
    unable to tell a checked report from an unchecked one.
    """
    failing = failing_claim_ids(result)
    for section in state.sections.as_list():
        hit = False
        for claim in section.claims:
            if claim.claim_id in failing:
                claim.verification_status = VerificationStatus.UNVERIFIED
                hit = True
        if hit:
            section.verification_status = VerificationStatus.UNVERIFIED
    return state


def retry_loop(
    state: ResearchState,
    result: VerificationResult,
    audit_again: Callable[[ResearchState], VerificationResult],
    rerun: Rerun,
    on_retry: Callable[[RetryDirective], None] | None = None,
) -> tuple[ResearchState, VerificationResult]:
    """Verify, retry, re-verify, up to MAX_ATTEMPTS, then mark and continue.

    `result.retries_issued` comes from the auditor: it names the directives, and stops issuing them
    once a section has used its attempts (it reads `section.retry_count`, which apply_directive
    increments). Two failure types are never retried and simply end up marked unverified:
    `recompute_mismatch` (a calc/ bug) and `future_fact` (a data/ bug).
    """
    for _ in range(MAX_ATTEMPTS):
        directives = [d for d in result.retries_issued if d.attempt <= d.max_attempts]
        if not directives:
            break
        for directive in directives:
            if on_retry:
                on_retry(directive)
            state = apply_directive(state, directive, rerun)
        result = audit_again(state)
    return mark_unverified(state, result), result


__all__ = [
    "MAX_ATTEMPTS",
    "VerificationIssue",
    "apply_directive",
    "directive_feedback",
    "mark_unverified",
    "retry_loop",
]
