"""Fixture-backed FactRepository. Powers MODE=mock with no database.

Specified by schema/contracts/interfaces.py (FactRepository).

Loads fixtures/mock/facts.json and applies the SAME point-in-time and
restatement filtering the Postgres implementation does. That matters: if mock
mode skipped those filters, every test would pass against data the live path
would never return.

TODO(roadmap Step 1, P1).
"""

from __future__ import annotations

from schema.contracts.common import FactId, ISODate, Ticker
from schema.contracts.facts import FinancialFact


class FixtureFactRepository:
    """In-memory FactRepository over the ACME fixtures."""

    def __init__(self, fixtures_dir: str | None = None) -> None:
        self.fixtures_dir = fixtures_dir
        raise NotImplementedError("TODO(roadmap Step 1, P1): load facts.json")

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
        """Newest first, filed on or before `as_of`, restatements excluded."""
        raise NotImplementedError("TODO(roadmap Step 1, P1)")

    def resolve_fact(self, fact_id: FactId, as_of: ISODate) -> FinancialFact | None:
        raise NotImplementedError("TODO(roadmap Step 1, P1)")

    def put_facts(self, facts: list[FinancialFact]) -> int:
        """Accepted and discarded: the fixture store is read-only."""
        raise NotImplementedError("TODO(roadmap Step 1, P1)")

    def latest_period(self, ticker: Ticker, as_of: ISODate, *, annual: bool = True) -> str | None:
        raise NotImplementedError("TODO(roadmap Step 1, P1)")
