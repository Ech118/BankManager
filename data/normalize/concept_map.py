"""Canonical metric name -> ordered list of candidate XBRL concepts.

Specified by docs/sec-pitfalls.md "Concept tag variance".

Filers tag the same economic quantity differently, and the same filer changes
tags between years. Resolution is ordered: try each candidate in turn and record
WHICH ONE matched on the fact's `xbrl_concept`, so a reviewer can see where a
number really came from.

A metric that resolves to nothing becomes an `unavailable` fact plus a
data_quality gap. It never becomes 0.

TODO(roadmap Step 1, P1): implement resolve(); extend the map from real filings.
"""

from __future__ import annotations

CONCEPTS: dict[str, tuple[str, ...]] = {
    "revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ),
    "cost_of_revenue": ("CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfServices"),
    "gross_profit": ("GrossProfit",),
    "operating_income": ("OperatingIncomeLoss",),
    "pretax_income": ("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
    "eps_diluted": ("EarningsPerShareDiluted", "IncomeLossFromContinuingOperationsPerDilutedShare"),
    "shares_diluted": ("WeightedAverageNumberOfDilutedSharesOutstanding",),
    "depreciation_amortization": (
        "DepreciationDepletionAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
    ),
    "op_cash_flow": (
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ),
    "capex": (
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ),
    "sbc": ("ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"),
    "cash": (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ),
    "total_debt": ("DebtLongtermAndShorttermCombinedAmount", "LongTermDebt"),
    "interest_expense": ("InterestExpense", "InterestExpenseDebt"),
    "total_assets": ("Assets",),
    "total_equity": ("StockholdersEquity",),
    "current_assets": ("AssetsCurrent",),
    "current_liabilities": ("LiabilitiesCurrent",),
    "receivables": ("AccountsReceivableNetCurrent",),
    "inventory": ("InventoryNet",),
}
"""Ordered candidates. Earlier entries win; the winner is recorded on the fact."""

SIGN_FLIPPED: frozenset[str] = frozenset({"capex"})
"""Concepts XBRL reports as an outflow that we store POSITIVE meaning cash spent
(CLAUDE.md sign conventions). Flipping here means calc/ never has to guess."""


def candidates(metric: str) -> tuple[str, ...]:
    """Ordered XBRL concepts to try for one canonical metric."""
    return CONCEPTS.get(metric, ())


def resolve(metric: str, available: dict[str, object]) -> tuple[str, object] | None:
    """Return (winning_concept, payload), or None when nothing matched."""
    raise NotImplementedError("TODO(roadmap Step 1, P1)")
