"""Valuation multiples: P/E, EV/EBITDA, EV/revenue, P/FCF.

Specified by docs/data-model.md "Valuation".

Enterprise value is recomputed from the market snapshot rather than trusted:
market_cap + total_debt - cash, from ONE snapshot instant. The verifier
re-derives it and raises RECOMPUTE_MISMATCH on drift.

TODO(roadmap Step 4, P2).
"""

from __future__ import annotations

from schema.contracts.common import ValueObject
from schema.contracts.factsheet import Factsheet
from schema.contracts.metrics import Metrics


def enterprise_value(factsheet: Factsheet) -> ValueObject:
    """market_cap + total_debt - cash, all from one snapshot."""
    raise NotImplementedError("TODO(roadmap Step 4, P2)")


def price_to_earnings(factsheet: Factsheet, period: str) -> ValueObject:
    """Trailing P/E from the latest full year's diluted EPS."""
    raise NotImplementedError("TODO(roadmap Step 4, P2)")


def forward_pe(factsheet: Factsheet) -> ValueObject:
    """Price / consensus next-FY EPS. Type ESTIMATE, never 'fact'."""
    raise NotImplementedError("TODO(roadmap Step 4, P2)")


def ev_ebitda(factsheet: Factsheet, metrics: Metrics) -> ValueObject:
    raise NotImplementedError("TODO(roadmap Step 4, P2)")


def ev_revenue(factsheet: Factsheet, period: str) -> ValueObject:
    raise NotImplementedError("TODO(roadmap Step 4, P2)")


def price_to_fcf(factsheet: Factsheet, metrics: Metrics) -> ValueObject:
    raise NotImplementedError("TODO(roadmap Step 4, P2)")
