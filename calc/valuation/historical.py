"""Historical multiples: how the company's own valuation has moved.

Specified by docs/data-model.md "Valuation".

A company at 34x earnings against a five-year median of 22x is a different
proposition from one at 34x against a median of 33x, even when the peer
comparison is identical. This is the comparison that is hardest to get for free
(error E), so every output may legitimately be `unavailable`.

TODO(roadmap Step 4, P2).
"""

from __future__ import annotations

from schema.contracts.common import ValueObject


def historical_median(series: list[ValueObject]) -> ValueObject:
    """Median of a company's own multiple over time."""
    raise NotImplementedError("TODO(roadmap Step 4, P2)")


def premium_to_own_history(current: ValueObject, history: list[ValueObject]) -> ValueObject:
    """Premium (+) or discount (-) to the company's own historical median."""
    raise NotImplementedError("TODO(roadmap Step 4, P2)")
