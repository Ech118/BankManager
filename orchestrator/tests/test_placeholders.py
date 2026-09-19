"""P3 orchestrator unit-test placeholders. Specified by docs/pipeline.md."""

import pytest


@pytest.mark.skip(reason="TODO(roadmap Step 1, P3): coordinator")
def test_out_of_scope_ticker_costs_zero_llm_calls():
    """check_scope runs first; a rejected company produces a clear refusal, not
    an analysis."""


@pytest.mark.skip(reason="TODO(roadmap Step 3, P3): parallel execution")
def test_financial_and_business_agents_run_concurrently():
    """Wall-clock must be the max of the two, not the sum."""


@pytest.mark.skip(reason="TODO(roadmap Step 1, P3): mcp client")
def test_mock_mode_speaks_real_mcp_not_a_shortcut():
    """The in-memory transport still goes through tool dispatch and argument
    validation, so the boundary is exercised in both modes."""


@pytest.mark.skip(reason="TODO(roadmap Step 1, P3): mcp client")
def test_invalid_tool_arguments_fail_in_p3_with_a_clear_message():
    """Validated against the contract request model before the call is made."""


@pytest.mark.skip(reason="TODO(roadmap Step 5, P3): retry loop")
def test_retry_targets_only_the_failing_section():
    """Agents that already passed are not re-run."""


@pytest.mark.skip(reason="TODO(roadmap Step 5, P3): retry loop")
def test_report_ships_after_the_retry_cap_with_claims_marked():
    """The run completes; the failing claims are labelled unverified."""


@pytest.mark.skip(reason="TODO(roadmap Step 2, P3): report generator")
def test_report_is_a_pure_function_of_the_state():
    """Same ResearchState, byte-identical report. No LLM in the renderer."""


@pytest.mark.skip(reason="TODO(roadmap Step 2, P3): report generator")
def test_unavailable_values_render_as_unavailable_not_zero():
    """A reader must be able to tell a missing number from a zero one."""


@pytest.mark.skip(reason="TODO(roadmap Step 2, P3): report generator")
def test_disclaimer_is_present_on_every_rendered_page():
    """Error M."""


@pytest.mark.skip(reason="TODO(roadmap Step 6, P3): redact hook")
def test_redact_is_applied_centrally_to_all_filing_text():
    """No agent can obtain un-redacted text by fetching a section itself."""
