"""P3 orchestrator unit-test placeholders. Specified by docs/pipeline.md."""

import pytest


@pytest.mark.skip(reason="TODO(roadmap Step 5, P3): retry loop")
def test_retry_targets_only_the_failing_section():
    """Agents that already passed are not re-run."""


@pytest.mark.skip(reason="TODO(roadmap Step 5, P3): retry loop")
def test_report_ships_after_the_retry_cap_with_claims_marked():
    """The run completes; the failing claims are labelled unverified."""


@pytest.mark.skip(reason="TODO(roadmap Step 6, P3): redact hook")
def test_redact_is_applied_centrally_to_all_filing_text():
    """No agent can obtain un-redacted text by fetching a section itself."""
