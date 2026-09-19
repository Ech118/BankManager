"""P2 audit unit-test placeholders. Specified by docs/verification.md.

The two that matter most are the adversarial ones: a gate that has never been
shown to catch an injected bad number is not known to work.
"""

import pytest


@pytest.mark.skip(reason="TODO(roadmap Step 2, P2): deterministic checks")
def test_audit_catches_an_injected_fake_number():
    """Change one number in a verdict so it no longer recomputes; the audit must
    fail with RECOMPUTE_MISMATCH naming expected and actual."""


@pytest.mark.skip(reason="TODO(roadmap Step 2, P2): quote checking")
def test_audit_catches_a_fabricated_quote():
    """A quote that does not appear in the cited section must raise
    UNSUPPORTED_CLAIM."""


@pytest.mark.skip(reason="TODO(roadmap Step 2, P2): deterministic checks")
def test_audit_catches_a_citation_to_a_superseded_fact():
    """Citing the as-filed FY2024 operating cash flow after it was restated must
    raise SUPERSEDED_FACT."""


@pytest.mark.skip(reason="TODO(roadmap Step 2, P2): deterministic checks")
def test_audit_catches_a_fact_from_after_the_as_of():
    """The backtest's integrity rests on this one (error A)."""


@pytest.mark.skip(reason="TODO(roadmap Step 2, P2): deterministic checks")
def test_audit_catches_prose_disagreeing_with_its_value_object():
    """Correct computation, wrong number in the sentence the reader sees."""


@pytest.mark.skip(reason="TODO(roadmap Step 2, P2): disclaimer")
def test_audit_fails_a_verdict_with_no_disclaimer():
    """Error M. Also covered by an e2e test."""


@pytest.mark.skip(reason="TODO(roadmap Step 2, P2): routing")
def test_retry_is_routed_to_the_section_owner():
    """A failure in the valuation section goes to the valuation agent, and to no
    one else."""


@pytest.mark.skip(reason="TODO(roadmap Step 2, P2): routing")
def test_retries_stop_at_the_cap_and_claims_ship_marked_unverified():
    """After two attempts the report ships, with the failing claims labelled
    rather than dropped."""


@pytest.mark.skip(reason="TODO(roadmap Step 2, P2): routing")
def test_recompute_mismatch_is_never_retried():
    """It is a calc/ bug; re-prompting an agent cannot fix it."""


@pytest.mark.skip(reason="TODO(roadmap Step 5, P2): llm verifier")
def test_verbatim_match_short_circuits_the_llm_check():
    """A quote that matches exactly must cost zero LLM calls."""
