"""P3 orchestrator unit-test placeholders. Specified by docs/pipeline.md."""

import pytest


@pytest.mark.skip(reason="TODO(roadmap Step 6, P3): redact hook")
def test_redact_is_applied_centrally_to_all_filing_text():
    """No agent can obtain un-redacted text by fetching a section itself."""
