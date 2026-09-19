"""Margin computation. Specified by docs/data-model.md.

All margins are FRACTIONS (0.40 means 40%). The contract rejects anything above
10 for a fraction unit, so a percent that escapes conversion fails loudly rather
than travelling into the report.

TODO(roadmap Step 2, P2).
"""

from __future__ import annotations

from schema.contracts.factsheet import Factsheet
from schema.contracts.metrics import Margins


def margins_for(factsheet: Factsheet, period: str) -> Margins:
    """Gross, operating, net and FCF margin for one period."""
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def all_margins(factsheet: Factsheet) -> dict[str, Margins]:
    """Margins for every reported period, keyed by period label."""
    raise NotImplementedError("TODO(roadmap Step 2, P2)")
