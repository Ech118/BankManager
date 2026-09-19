"""P3 agent unit-test placeholders. Specified by docs/pipeline.md."""

import pytest


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
