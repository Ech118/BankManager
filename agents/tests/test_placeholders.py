"""P3 agent unit-test placeholders. Specified by docs/pipeline.md."""

import pytest


@pytest.mark.skip(reason="TODO(roadmap Step 1, P3): base agent")
def test_invalid_agent_output_is_retried_once_then_fails_loudly():
    """Malformed JSON is reprompted with the validation error, then raises with
    the raw text logged. It is never silently dropped."""


@pytest.mark.skip(reason="TODO(roadmap Step 1, P3): base agent")
def test_finding_without_evidence_is_dropped_and_logged():
    """Error I. The drop must be visible in the run log."""


@pytest.mark.skip(reason="TODO(roadmap Step 1, P3): base agent")
def test_agent_number_without_a_fact_id_never_becomes_a_claim():
    """The no-bare-numbers rule, at the point it actually bites."""


@pytest.mark.skip(reason="TODO(roadmap Step 1, P3): base agent")
def test_redact_hook_is_applied_before_any_model_call():
    """An agent must not be able to bypass anonymization by fetching its own
    section text (error A)."""


@pytest.mark.skip(reason="TODO(roadmap Step 1, P3): base agent")
def test_filing_text_is_wrapped_as_untrusted_data():
    """Every section handed to a model carries the do-not-follow-instructions
    wrapper (error F)."""


@pytest.mark.skip(reason="TODO(roadmap Step 5, P3): red team")
def test_red_team_receives_the_raw_factsheet_not_just_summaries():
    """Otherwise it restates the other agents in a sceptical tone (error J)."""


@pytest.mark.skip(reason="TODO(roadmap Step 5, P3): scenario agent")
def test_scenario_agent_never_emits_a_probability_of_beating_the_index():
    """It proposes weights and a shift; calc/ decides (error C)."""


@pytest.mark.skip(reason="TODO(roadmap Step 5, P3): synthesizer")
def test_synthesizer_must_respond_to_every_red_team_point():
    """An empty response invalidates the verdict."""


@pytest.mark.skip(reason="TODO(roadmap Step 5, P3): synthesizer")
def test_synthesizer_verdict_must_agree_with_calc():
    """A strong_buy over a below-index expected return fails consistency."""


@pytest.mark.skip(reason="TODO(roadmap Step 1, P3): mcp client")
def test_agents_reach_data_only_through_mcp():
    """No agent module may import data/ or calc/ (ADR 0007)."""
