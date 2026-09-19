"""Year-over-year growth. Specified by docs/data-model.md.

Only emitted where a genuinely comparable prior period exists. Comparing a
quarter to a full year, or to a quarter of a different length, produces a number
that looks meaningful and is not, so the absence of a comparable prior yields no
entry rather than a plausible-looking one.

TODO(roadmap Step 2, P2).
"""

from __future__ import annotations

from schema.contracts.factsheet import Factsheet
from schema.contracts.metrics import Growth


def growth_for(factsheet: Factsheet, period: str, prior: str) -> Growth:
    """Revenue, EPS and FCF growth between two comparable periods."""
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def all_growth(factsheet: Factsheet) -> dict[str, Growth]:
    """Growth for every period that has a comparable prior."""
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def comparable_prior(factsheet: Factsheet, period: str) -> str | None:
    """The prior period of the same TYPE and length, or None."""
    raise NotImplementedError("TODO(roadmap Step 2, P2)")
