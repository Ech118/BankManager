"""Stock-based compensation and share-count dilution.

Specified by docs/data-model.md and docs/verification.md (adjusted_as_gaap).

This pair answers "is EPS growth real?". A company can grow EPS with no
operating improvement at all by buying back stock, and can flatter operating
income by excluding a compensation expense it pays every year. Both are legal,
disclosed, and easy to miss in a summary, so both are computed explicitly rather
than left for an agent to notice.

`dilution_yoy` is negative when the share count SHRANK.

TODO(roadmap Step 2, P2).
"""

from __future__ import annotations

from schema.contracts.common import ValueObject
from schema.contracts.factsheet import Factsheet


def dilution_yoy(factsheet: Factsheet, period: str, prior: str) -> ValueObject:
    """Change in diluted share count. Negative means buybacks shrank it."""
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def sbc_pct_revenue(factsheet: Factsheet, period: str) -> ValueObject:
    """SBC / revenue. Above config.SBC_REVENUE_FLAG raises a quality flag."""
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def sbc_pct_fcf(factsheet: Factsheet, period: str) -> ValueObject:
    """SBC / FCF. The harsher framing: what share of cash generation is paid in stock."""
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def eps_growth_attribution(factsheet: Factsheet, period: str, prior: str) -> dict:
    """Split EPS growth into the part from earnings and the part from buybacks.

    Computed here rather than asserted by an agent: the mock audit fixture
    carries a warning about exactly this number being rounded by an agent
    instead of recomputed.
    """
    raise NotImplementedError("TODO(roadmap Step 2, P2)")
