"""P2 calc unit-test placeholders. Each becomes a real test at the named step.

The cap and clamp tests are the ones that matter most: they are what stop an
agent from writing its own probabilities (error C, amendment 1).
"""

import pytest


@pytest.mark.skip(reason="TODO(roadmap Step 2, P2): compute_metrics")
def test_metrics_match_hand_checked_acme_numbers():
    """Every assert in scripts/gen_mock_fixtures.py must hold when calc/ computes
    the same values from the factsheet."""


@pytest.mark.skip(reason="TODO(roadmap Step 2, P2): compute_metrics")
def test_metrics_match_a_real_filing():
    """One hand-checked real company, so the mock cannot hide a formula error."""


@pytest.mark.skip(reason="TODO(roadmap Step 2, P2): missing inputs")
def test_missing_input_yields_unavailable_not_zero():
    """A metric whose input is unavailable must be unavailable, never 0."""


@pytest.mark.skip(reason="TODO(roadmap Step 2, P2): weight bounding")
def test_out_of_band_weight_is_clamped_not_rejected():
    """bear=0.55 with default 0.30 and band 0.15 clamps to 0.45, and the three
    applied weights still sum to 1."""


@pytest.mark.skip(reason="TODO(roadmap Step 2, P2): weight bounding")
def test_clamped_weight_is_recorded_in_the_result():
    """was_clamped is True and requested/clamped_to/applied are all preserved."""


@pytest.mark.skip(reason="TODO(roadmap Step 2, P2): weight bounding")
def test_redistribution_keeps_every_weight_inside_its_band():
    """Naive renormalization would push the clamped weight back out; the residual
    must go to the unclamped weights only."""


@pytest.mark.skip(reason="TODO(roadmap Step 2, P2): weight bounding")
def test_weights_that_do_not_sum_to_one_are_rejected():
    """A proposal that is not a distribution is an agent bug, not something to
    silently normalize."""


@pytest.mark.skip(reason="TODO(roadmap Step 2, P2): prior cap")
def test_prior_shift_cannot_exceed_the_cap():
    """The cap test. An agent requesting -0.9 moves the prior by at most the cap."""


@pytest.mark.skip(reason="TODO(roadmap Step 2, P2): prior cap")
def test_red_team_and_scenario_shifts_sum_before_the_cap_applies():
    """Two agents must not be able to exceed the cap by splitting a request."""


@pytest.mark.skip(reason="TODO(roadmap Step 4, P2): reverse DCF")
def test_reverse_dcf_always_returns_a_sensitivity_grid():
    """A single point answer is never acceptable (error D)."""


@pytest.mark.skip(reason="TODO(roadmap Step 4, P2): reverse DCF")
def test_terminal_growth_above_discount_rate_raises():
    """An infinite terminal value must fail loudly, not return a huge number."""


@pytest.mark.skip(reason="TODO(roadmap Step 2, P2): rubric")
def test_rubric_is_monotonic_in_excess_return():
    """A better excess return can never produce a worse score."""


@pytest.mark.skip(reason="TODO(roadmap Step 2, P2): consistency")
def test_strong_buy_below_the_index_is_inconsistent():
    """The headline may not contradict the table."""


@pytest.mark.skip(reason="TODO(roadmap Step 4, P2): peers")
def test_peer_median_ignores_unavailable_multiples():
    """And the usable peer count is reported, so a thin comparison looks thin."""
