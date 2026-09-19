"""Working-capital quality: receivables, inventory, and the balance sheet.

Specified by docs/data-model.md.

Receivables growing faster than revenue is the classic early warning: it can
mean longer payment terms granted to close deals, or revenue recognised before
cash is likely to arrive. Either way it is visible in the numbers a quarter or
two before it is visible in earnings, which is why it is computed rather than
left to prose.

TODO(roadmap Step 2, P2).
"""

from __future__ import annotations

from schema.contracts.common import ValueObject
from schema.contracts.factsheet import Factsheet
from schema.contracts.metrics import BalanceSheet, QualityFlag


def days_sales_outstanding(factsheet: Factsheet, period: str) -> ValueObject:
    """receivables / revenue * 365."""
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def days_inventory(factsheet: Factsheet, period: str) -> ValueObject:
    """inventory / cost_of_revenue * 365."""
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def balance_sheet_metrics(factsheet: Factsheet) -> BalanceSheet:
    """Net debt, leverage, interest coverage and the current ratio.

    Uses the LATEST REPORTED BALANCE SHEET, which may be a quarter, while flow
    metrics use the latest full year.
    """
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def quality_flags(factsheet: Factsheet) -> list[QualityFlag]:
    """Deterministic earnings-quality warnings, against config.py thresholds.

    Each flag states what was observed with its numbers, so a reader can judge
    it rather than trusting the label.
    """
    raise NotImplementedError("TODO(roadmap Step 2, P2)")
