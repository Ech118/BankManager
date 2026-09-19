"""Free cash flow and its derivatives. Specified by docs/data-model.md.

FCF = op_cash_flow - capex, with capex POSITIVE meaning cash spent (CLAUDE.md
sign conventions). P1 normalizes the sign, so nothing here has to guess.

`fcf_conversion` (FCF / net income) is the quiet one: a company whose reported
profit stops turning into cash is usually the first sign of an accounting
problem, well before anything shows up in the income statement.

TODO(roadmap Step 2, P2).
"""

from __future__ import annotations

from schema.contracts.common import ValueObject
from schema.contracts.factsheet import Factsheet


def free_cash_flow(factsheet: Factsheet, period: str) -> ValueObject:
    """op_cash_flow - capex for one period."""
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def fcf_conversion(factsheet: Factsheet, period: str) -> ValueObject:
    """FCF / net income. Below config.FCF_CONVERSION_FLAG raises a quality flag."""
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def fcf_yield(factsheet: Factsheet, period: str) -> ValueObject:
    """FCF / market cap. The valuation metric least sensitive to accounting choices."""
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def capex_intensity(factsheet: Factsheet, period: str) -> ValueObject:
    """Capex / revenue. How much growth has to be bought."""
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def ebitda(factsheet: Factsheet, period: str) -> ValueObject:
    """Operating income + D&A, UNADJUSTED.

    Deliberately not "adjusted EBITDA": every company adjusts differently, and
    an adjusted figure presented as a standard one is exactly what
    IssueType.ADJUSTED_AS_GAAP exists to catch.
    """
    raise NotImplementedError("TODO(roadmap Step 2, P2)")
