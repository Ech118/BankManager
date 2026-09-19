"""Postgres FactRepository with point-in-time queries. MODE=live only.

Specified by schema/contracts/interfaces.py (FactRepository) and docs/adr/0003.

THE ONE QUERY THAT MATTERS: for each (metric, fiscal_period), return the value
from the LATEST FILING FILED ON OR BEFORE `as_of` - not the latest filing
overall. Getting that wrong turns every backtest into a look-ahead.

TODO(roadmap Step 1, P1): implement.
TODO(roadmap Step 2, P1): restatement-aware as-of selection.
"""

from __future__ import annotations

from schema.contracts.common import FactId, ISODate, Ticker
from schema.contracts.facts import FinancialFact


class PostgresFactRepository:
    """FactRepository backed by the financial_facts table."""

    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = dsn
        raise NotImplementedError("TODO(roadmap Step 1, P1)")

    def get_facts(
        self,
        ticker: Ticker,
        metrics: list[str],
        as_of: ISODate,
        *,
        period_type: str | None = None,
        periods: int | None = None,
        include_superseded: bool = False,
    ) -> list[FinancialFact]:
        """Point-in-time read.

        Sketch of the query (TODO Step 2 to finish):
            SELECT DISTINCT ON (metric, fiscal_period) *
            FROM financial_facts
            WHERE ticker = %s AND metric = ANY(%s) AND filed_at <= %s
            ORDER BY metric, fiscal_period, filed_at DESC
        DISTINCT ON picks the most recent filing that existed at `as_of`, which
        is exactly the as-filed value when `as_of` predates a restatement.
        """
        raise NotImplementedError("TODO(roadmap Step 1, P1)")

    def resolve_fact(self, fact_id: FactId, as_of: ISODate) -> FinancialFact | None:
        raise NotImplementedError("TODO(roadmap Step 1, P1)")

    def put_facts(self, facts: list[FinancialFact]) -> int:
        """Upsert, then link restatements via data.normalize.restatements."""
        raise NotImplementedError("TODO(roadmap Step 2, P1)")

    def latest_period(self, ticker: Ticker, as_of: ISODate, *, annual: bool = True) -> str | None:
        raise NotImplementedError("TODO(roadmap Step 1, P1)")
