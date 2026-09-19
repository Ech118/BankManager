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

from collections.abc import Callable

from schema.contracts.claims import Claim
from schema.contracts.state import ResearchState
from schema.contracts.verification import VerificationIssue


def quote_matches_verbatim(claim: Claim, get_text: Callable[[str], str]) -> bool:
    """Whitespace-normalised substring match of each quote in its source.

    The free path. Only a failure here justifies spending an LLM call.
    """
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def check_unsupported_claims(
    state: ResearchState,
    get_text: Callable[[str], str],
    verify_claim: Callable[[str, str], bool] | None = None,
) -> list[VerificationIssue]:
    """Every qualitative claim must be supported by the passage it cites.

    Verbatim match first. Only on failure, and only when `verify_claim` is
    supplied, ask the model whether the passage still supports the claim. With
    no `verify_claim`, a failed match is reported as unsupported - the safe
    direction, since the alternative is passing an unchecked claim.

    Issues from this path are marked `checked_by_llm=True`, which the contract
    permits only for this issue type.
    """
    raise NotImplementedError("TODO(roadmap Step 5, P2)")
