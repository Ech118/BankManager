"""Reverse DCF: what growth does today's price already assume?

Specified by docs/data-model.md and docs/adr/0001.

The most useful question in the product. A forward DCF asks "what is it worth?",
which mostly returns the analyst's own assumptions. A reverse DCF asks "what
would have to be true for today's price to be right?" and hands the LLM
something it is actually good at: judging whether that is plausible given the
filings.

Solves for the FCF growth rate that makes PV equal enterprise value, by
bisection on a monotonic function.

TODO(roadmap Step 4, P2).
"""

from __future__ import annotations

from schema.contracts.factsheet import Factsheet
from schema.contracts.metrics import Metrics, ReverseDcf


def implied_growth(
    enterprise_value: float,
    fcf0: float,
    discount_rate: float,
    terminal_growth: float,
    years: int,
) -> float:
    """Bisect for the growth rate whose PV equals `enterprise_value`."""
    raise NotImplementedError("TODO(roadmap Step 4, P2)")


def reverse_dcf(
    factsheet: Factsheet, metrics: Metrics, assumptions: dict | None = None
) -> ReverseDcf:
    """Implied FCF CAGR plus the full sensitivity grid.

    `assumptions` may override config.py, and overrides are tagged ASSUMPTION
    with a src:config: source so the report can colour them.

    Takes no `as_of`: the factsheet carries it (amendment 2).
    """
    raise NotImplementedError("TODO(roadmap Step 4, P2)")
