"""Canonical metric name -> ordered list of candidate XBRL concepts.

Specified by docs/sec-pitfalls.md "Concept tag variance".

Filers tag the same economic quantity differently, and the same filer changes
tags between years. Resolution is ordered: try each candidate in turn and record
WHICH ONE matched on the fact's `xbrl_concept`, so a reviewer can see where a
number really came from.

A metric that resolves to nothing becomes an `unavailable` fact plus a
data_quality gap. It never becomes 0.

RESOLUTION IS PER FISCAL PERIOD, NOT PER COMPANY
    Surveyed against the real filings of AAPL, MSFT, NVDA, AMZN, GOOGL, KO,
    WDFC, JPM and O. A chain resolved once for a company loses years:

      NVDA capex   PaymentsToAcquirePropertyPlantAndEquipment  FY2010-FY2012
                   PaymentsToAcquireProductiveAssets           FY2022-FY2026
      AAPL revenue SalesRevenueNet                             FY2007-FY2017
                   RevenueFromContractWithCustomer...          FY2017-FY2025
      KO   debt    LongTermDebt                                through FY2023
                   LongTermDebtAndCapitalLeaseObligations      FY2024 onward

    So `resolve()` takes one period's facts and answers for that period alone.

TAXONOMY
    METRIC_CHAINS is keyed by taxonomy so an `ifrs-full` map can be added for
    20-F/40-F filers without touching the resolver. Only `us-gaap` is built:
    a foreign private issuer currently returns `unavailable` through
    normalize.scope, which labels it `partial` rather than pretending.
"""

from __future__ import annotations

from dataclasses import dataclass

Chain = tuple[str, ...]
"""Ordered candidates for one metric. Earlier entries win."""

US_GAAP = "us-gaap"
IFRS_FULL = "ifrs-full"

METRIC_CHAINS: dict[str, dict[str, Chain]] = {
    US_GAAP: {
        "revenue": (
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
            "Revenues",
            "RevenuesNetOfInterestExpense",
            "SalesRevenueNet",
        ),
        "cost_of_revenue": (
            "CostOfRevenue",
            "CostOfGoodsAndServicesSold",
            "CostOfServices",
            "CostOfGoodsSold",
        ),
        "gross_profit": ("GrossProfit",),
        "operating_income": ("OperatingIncomeLoss",),
        "pretax_income": (
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic",
        ),
        "net_income": ("NetIncomeLoss", "ProfitLoss"),
        "eps_diluted": (
            "EarningsPerShareDiluted",
            "IncomeLossFromContinuingOperationsPerDilutedShare",
        ),
        "shares_diluted": (
            "WeightedAverageNumberOfDilutedSharesOutstanding",
            "WeightedAverageNumberOfSharesOutstandingBasic",
        ),
        "depreciation_amortization": (
            "DepreciationDepletionAndAmortization",
            "DepreciationAmortizationAndAccretionNet",
            "DepreciationAndAmortization",
            "Depreciation",
        ),
        "op_cash_flow": (
            "NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        ),
        "capex": (
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "PaymentsToAcquireProductiveAssets",
            "PaymentsToAcquireCommercialRealEstate",
            "PaymentsToAcquireRealEstate",
        ),
        "sbc": ("ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"),
        "cash": (
            "CashAndCashEquivalentsAtCarryingValue",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        ),
        "interest_expense": (
            "InterestExpense",
            "InterestExpenseNonoperating",
            "InterestExpenseDebt",
            "InterestAndDebtExpense",
            "InterestIncomeExpenseNet",
        ),
        "total_assets": ("Assets",),
        "total_equity": (
            "StockholdersEquity",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        ),
        "current_assets": ("AssetsCurrent",),
        "current_liabilities": ("LiabilitiesCurrent",),
        "receivables": (
            "AccountsReceivableNetCurrent",
            "ReceivablesNetCurrent",
            "AccountsAndOtherReceivablesNetCurrent",
        ),
        "inventory": ("InventoryNet", "InventoryGross"),
        "shares_outstanding": ("CommonStockSharesOutstanding",),
        "stock_split_ratio": (
            "StockholdersEquityNoteStockSplitConversionRatio1",
            "StockholdersEquityNoteStockSplitConversionRatio",
        ),
    },
    IFRS_FULL: {},
    # Deliberately empty. A 20-F/40-F filer has no us-gaap node at all (TSM's
    # companyfacts carries only dei, ifrs-full and srt), so it is reported as
    # `partial` by normalize.scope rather than silently returning nothing.
}
"""taxonomy -> metric -> ordered candidates. The winner lands on the fact."""

NON_ANNUAL_METRICS: frozenset[str] = frozenset({"shares_outstanding", "stock_split_ratio"})
"""Metrics not resolved from the annual 10-K loop.

`shares_outstanding` is a cover-page fact the market snapshot reads
(data/ingest/market_client.py). `stock_split_ratio` is an event, tagged in
whichever filing followed the split - NVDA reported its 10-for-1 ratio in a
10-Q and never in a 10-K - so data/normalize/splits.py reads every form."""

INSTANT_METRICS: frozenset[str] = frozenset(
    {
        "cash",
        "total_assets",
        "total_equity",
        "current_assets",
        "current_liabilities",
        "receivables",
        "inventory",
        "shares_outstanding",
        "total_debt",
    }
)
"""Balance-sheet metrics: an XBRL `instant` with no period_start."""

SIGN_FLIPPED: frozenset[str] = frozenset({"capex"})
"""Concepts XBRL reports as an outflow that we store POSITIVE meaning cash spent
(CLAUDE.md sign conventions). Flipping here means calc/ never has to guess.

NOTE: the SEC's cash-flow capex tags are already reported positive (a payment),
so nothing is flipped in practice today. The set stays because a filer that
reports the outflow negative would otherwise produce a negative FCF drag that
looks like a cash inflow.
"""

TOTAL_DEBT = "total_debt"
"""Handled by resolve_total_debt(), not by a plain chain: most filers never
report a single total-debt line, so it is summed from disjoint components."""


# --------------------------------------------------------------------------
# debt
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class DebtBucket:
    """One way a filer reports the long-term half of its debt.

    `covers_current` records whether `primary` ALREADY includes current
    maturities, which is the difference between a correct total and a 12%
    overstatement:

      AAPL  LongTermDebt 90,678 == LongTermDebtNoncurrent 78,328
                                 + LongTermDebtCurrent    12,350
      NVDA  DebtCurrent 999 is the SAME 999 as LongTermDebtCurrent, and
            LongTermDebt 8,468 already contains it.
      KO    LongTermDebtAndCapitalLeaseObligations is NONCURRENT: its FY2023
            value 35,547 equals LongTermDebtNoncurrent, not the 37,507 total.
    """

    primary: str
    current_part: str | None = None
    covers_current: bool = False


TOTAL_DEBT_CONCEPTS: Chain = ("DebtLongtermAndShorttermCombinedAmount",)
"""A genuine reported total. WDFC: 86,995 == LongTermDebt 86,195 + ST 800."""

LONG_TERM_DEBT_BUCKETS: tuple[DebtBucket, ...] = (
    DebtBucket("LongTermDebt", covers_current=True),
    DebtBucket(
        "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
        covers_current=True,
    ),
    DebtBucket(
        "LongTermDebtAndCapitalLeaseObligations",
        current_part="LongTermDebtAndCapitalLeaseObligationsCurrent",
    ),
    DebtBucket("LongTermDebtNoncurrent", current_part="LongTermDebtCurrent"),
    DebtBucket("NotesPayable", covers_current=True),
)
"""Ordered. `NotesPayable` is a last resort reached only by filers that tag no
long-term debt at all - in the survey, only the REIT (O: 25,032M of notes)."""


@dataclass(frozen=True)
class ShortTermDebtGroup:
    """Short-term borrowings that are NOT already inside the long-term bucket."""

    concepts: Chain
    only_if_current_uncovered: bool = False


SHORT_TERM_DEBT_GROUPS: tuple[ShortTermDebtGroup, ...] = (
    ShortTermDebtGroup(("ShortTermBorrowings",)),
    ShortTermDebtGroup(("CommercialPaper", "OtherShortTermBorrowings")),
    ShortTermDebtGroup(("DebtCurrent",), only_if_current_uncovered=True),
)
"""Ordered; the first group with any member present wins, and all present
members of that group are summed (KO reports CommercialPaper AND
OtherShortTermBorrowings as separate lines).

`DebtCurrent` is guarded: for NVDA and WDFC it restates current maturities the
long-term bucket already counted."""

EXCLUDED_FROM_TOTAL_DEBT: frozenset[str] = frozenset(
    {
        "FinanceLeaseLiability",
        "FinanceLeaseLiabilityCurrent",
        "FinanceLeaseLiabilityNoncurrent",
        "LongTermDebtFairValue",
    }
)
"""Finance leases are excluded consistently across filers, and fair value is a
disclosure, not the carrying amount. Listed so the choice is visible rather
than implicit in the absence of a tag."""


def candidates(metric: str, taxonomy: str = US_GAAP) -> Chain:
    """Ordered XBRL concepts to try for one canonical metric."""
    return METRIC_CHAINS.get(taxonomy, {}).get(metric, ())


def metrics(taxonomy: str = US_GAAP) -> tuple[str, ...]:
    """Every canonical metric this taxonomy can resolve, total_debt included."""
    return (*METRIC_CHAINS.get(taxonomy, {}), TOTAL_DEBT)


def all_concepts(taxonomy: str = US_GAAP) -> tuple[str, ...]:
    """Every concept any chain might ask for. Used to trim recorded fixtures."""
    seen: dict[str, None] = {}
    for chain in METRIC_CHAINS.get(taxonomy, {}).values():
        for concept in chain:
            seen[concept] = None
    for concept in TOTAL_DEBT_CONCEPTS:
        seen[concept] = None
    for bucket in LONG_TERM_DEBT_BUCKETS:
        seen[bucket.primary] = None
        if bucket.current_part:
            seen[bucket.current_part] = None
    for group in SHORT_TERM_DEBT_GROUPS:
        for concept in group.concepts:
            seen[concept] = None
    for concept in EXCLUDED_FROM_TOTAL_DEBT:
        seen[concept] = None
    return tuple(seen)


def resolve(metric: str, available: dict[str, object], taxonomy: str = US_GAAP):
    """Return (winning_concept, payload), or None when nothing matched.

    `available` maps concept name -> whatever the caller holds for ONE fiscal
    period (normalize.to_facts passes the raw companyfacts entry).
    """
    for concept in candidates(metric, taxonomy):
        payload = available.get(concept)
        if payload is not None:
            return concept, payload
    return None


@dataclass(frozen=True)
class DebtComponent:
    """One reported line that goes into a summed total debt."""

    concept: str
    payload: object


def resolve_total_debt(
    available: dict[str, object], taxonomy: str = US_GAAP
) -> tuple[DebtComponent, ...]:
    """Components of total debt for ONE fiscal period, or () when none resolve.

    A single component means the filer reported a real total; several mean it is
    a sum, and every one of them is emitted as its own fact so the UI can make
    the parts of the total clickable (data/normalize/to_facts.py).
    """
    if taxonomy != US_GAAP:
        return ()

    for concept in TOTAL_DEBT_CONCEPTS:
        payload = available.get(concept)
        if payload is not None:
            return (DebtComponent(concept, payload),)

    components: list[DebtComponent] = []
    current_covered = False

    for bucket in LONG_TERM_DEBT_BUCKETS:
        payload = available.get(bucket.primary)
        if payload is None:
            continue
        components.append(DebtComponent(bucket.primary, payload))
        current_covered = bucket.covers_current
        if bucket.current_part:
            current_payload = available.get(bucket.current_part)
            if current_payload is not None:
                components.append(DebtComponent(bucket.current_part, current_payload))
                current_covered = True
        break

    for group in SHORT_TERM_DEBT_GROUPS:
        if group.only_if_current_uncovered and current_covered:
            continue
        found = [
            DebtComponent(concept, available[concept])
            for concept in group.concepts
            if available.get(concept) is not None
        ]
        if found:
            components.extend(found)
            break

    return tuple(components)
