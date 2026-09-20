"""End-to-end placeholders. Specified by docs/roadmap.md checkpoints.

These are the tests that decide whether a checkpoint is actually met. Each one
corresponds to a line in the roadmap, so "Step 3 is done" has a definition
rather than an opinion.
"""

import pytest


@pytest.mark.skip(reason="TODO(roadmap Step 3 checkpoint): live thin slice")
def test_one_real_ticker_financial_and_business_sections_in_live_mode():
    """Step 3 checkpoint."""


@pytest.mark.skip(reason="TODO(roadmap Step 4 checkpoint): live valuation")
def test_live_valuation_section_passes_verification():
    """Step 4 checkpoint."""


@pytest.mark.skip(reason="TODO(roadmap Step 5 checkpoint): full live report")
def test_full_live_report_passes_audit():
    """Step 5 checkpoint: all six agents, verification, retry loop."""
