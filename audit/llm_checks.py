"""The LLM half of the verification gate. Exactly one check.

Specified by docs/verification.md and docs/adr/0005.

UNSUPPORTED_CLAIM is the only issue type that needs a model, and even it tries
not to. A verbatim string match against the cited section text settles most
cases for free; the model is consulted only when the match fails, to judge
whether a faithful paraphrase is still supported by the passage.

Keeping this list at one entry is deliberate. Every LLM check costs money, adds
latency, and can itself be wrong - a verifier that hallucinates is worse than no
verifier, because it launders a bad claim as checked.

The model is INJECTED as a callable, so audit/ depends on no SDK and the whole
gate is testable with a stub.

TODO(roadmap Step 5, P2).
"""

from __future__ import annotations

import re
from collections.abc import Callable

from schema.contracts.claims import Claim
from schema.contracts.enums import IssueType, Severity
from schema.contracts.state import ResearchState
from schema.contracts.verification import VerificationIssue


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def quote_matches_verbatim(claim: Claim, get_text: Callable[[str], str]) -> bool:
    """Whitespace-normalised substring match of each quote in its source.

    The free path. Only a failure here justifies spending an LLM call. A claim
    with no evidence at all has nothing to check here (the Claim model already
    requires evidence or section_ids for a qualitative agent claim).
    """
    for ev in claim.evidence:
        try:
            text = get_text(ev.source_id)
        except KeyError:
            return False
        if _norm(ev.quote) not in _norm(text):
            return False
    return True


def check_unsupported_claims(
    state: ResearchState,
    get_text: Callable[[str], str],
    verify_claim: Callable[[str, str], bool] | None = None,
) -> tuple[list[VerificationIssue], int]:
    """Every qualitative claim must be supported by the passage it cites.

    Verbatim match first. Only on failure, and only when `verify_claim` is
    supplied, ask the model whether the passage still supports the claim. With
    no `verify_claim`, a failed match is reported as unsupported - the safe
    direction, since the alternative is passing an unchecked claim.

    Issues from this path are marked `checked_by_llm=True`, which the contract
    permits only for this issue type. Returns (issues, llm_calls_made) - the
    call count is cost tracking (error K) and must stay small.
    """
    issues = []
    llm_calls = 0
    for section in state.sections.as_list():
        for claim in section.claims:
            if not claim.evidence:
                continue
            if quote_matches_verbatim(claim, get_text):
                continue

            checked_by_llm = False
            supported = False
            if verify_claim is not None:
                checked_by_llm = True
                llm_calls += 1
                passage = ""
                for ev in claim.evidence:
                    try:
                        passage += get_text(ev.source_id) + "\n"
                    except KeyError:
                        pass
                try:
                    supported = bool(verify_claim(claim.text, passage))
                except Exception:  # noqa: BLE001 - fails closed (docs/verification.md)
                    supported = False

            if not supported:
                issues.append(VerificationIssue(
                    issue_type=IssueType.UNSUPPORTED_CLAIM, severity=Severity.ERROR,
                    path=f"sections.{section.section_key}",
                    message=f"{claim.claim_id}: cited passage does not support this claim",
                    claim_id=claim.claim_id,
                    checked_by_llm=checked_by_llm,
                ))
    return issues, llm_calls
