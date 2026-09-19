"""Scenario evaluation: where LLM proposals become bounded numbers.

Specified by docs/pipeline.md and docs/adr/0001.

The Scenario Agent proposes cases, weights and a prior shift, each with a
written reason. This package decides what is actually used:

  evaluate.py   clamps the weights into their band, redistributes, and records
                every clamp
  prior.py      applies the capped prior shift to the historical base rate
  rubric.py     maps excess return to a 1-10 score
  consistency.py checks the score, probability, return and verdict agree

No LLM output reaches the reader without passing through here.
"""
