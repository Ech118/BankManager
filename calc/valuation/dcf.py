"""Discounted cash flow. Specified by docs/data-model.md and docs/adr/0001.

Every output is dominated by its assumptions, so every output ships with a
sensitivity grid. A single headline number would imply a precision this method
does not have (error D).

TODO(roadmap Step 4, P2).
"""

from __future__ import annotations

from schema.contracts.metrics import SensitivityRow


def present_value(
    fcf0: float, growth: float, discount_rate: float, terminal_growth: float, years: int
) -> float:
    """PV of a growing FCF stream plus a terminal value.

    Requires terminal_growth < discount_rate; otherwise the terminal value is
    infinite and the model is meaningless. Raises ValueError rather than
    returning a huge number that looks like an answer.
    """
    raise NotImplementedError("TODO(roadmap Step 4, P2)")


def sensitivity_grid(fcf0: float, target_value: float, years: int) -> list[SensitivityRow]:
    """Solve across the config.py discount-rate and terminal-growth axes.

    The spread across this grid is the honest answer; the centre cell alone is
    not.
    """
    raise NotImplementedError("TODO(roadmap Step 4, P2)")
