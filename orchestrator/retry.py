"""Targeted retry execution. Specified by docs/verification.md.

audit/routing.py decides WHICH agent gets a retry; this module runs it.

The rule: re-run one agent for one section, with the failures explained in the
prompt, at most twice. Not the whole pipeline - a full rerun re-rolls agents
that already passed, costs seven LLM calls instead of one, and makes the run
non-reproducible for no benefit (error K).

After the cap the claims ship marked `unverified`. That is the deliberate
choice: a report with two labelled unverified claims is more useful, and more
honest, than no report.

TODO(roadmap Step 5, P3).
"""

from __future__ import annotations

from schema.contracts.state import ResearchState
from schema.contracts.verification import RetryDirective, VerificationResult

MAX_ATTEMPTS = 2
"""Matches schema.contracts.verification.MAX_RETRIES."""


def apply_directive(state: ResearchState, directive: RetryDirective, mcp: object) -> ResearchState:
    """Re-run one agent for one section with the issues fed back into its prompt."""
    raise NotImplementedError("TODO(roadmap Step 5, P3)")


def mark_unverified(state: ResearchState, result: VerificationResult) -> ResearchState:
    """Mark claims that failed after the cap, so the report can label them.

    The report renders these visibly. A claim that quietly disappeared would
    leave the reader unable to tell a checked report from an unchecked one.
    """
    raise NotImplementedError("TODO(roadmap Step 5, P3)")


def retry_loop(
    state: ResearchState, result: VerificationResult, mcp: object
) -> tuple[ResearchState, VerificationResult]:
    """Verify, retry, re-verify, up to MAX_ATTEMPTS, then mark and continue."""
    raise NotImplementedError("TODO(roadmap Step 5, P3)")
