"""Fixture-backed FactRepository. Powers MODE=mock with no database.

Specified by schema/contracts/interfaces.py (FactRepository) and docs/adr/0003.

Loads fixtures/mock/facts.json and applies the SAME point-in-time and
restatement filtering the Postgres implementation will. That matters: if mock
mode skipped those filters, every test would pass against data the live path
would never return.

THE ONE ALGORITHM THAT MATTERS (docs/adr/0003):

    For each (metric, fiscal_period), return the value from the LATEST FILING
    FILED ON OR BEFORE as_of - not the latest filing overall.

`superseded_by` is a fact about TODAY, not about `as_of`. On 2025-06-01 the
as-filed FY2024 operating cash flow of $690M was the current figure; it only
became superseded when the FY2025 10-K restated it on 2026-02-20. So the filter
is by filing date first, and "superseded" is decided relative to what was
visible at `as_of` - never by reading `superseded_by` directly.
"""

from __future__ import annotations

import json
from pathlib import Path

from schema.contracts.common import FactId, ISODate, Ticker
from schema.contracts.enums import SourceKind
from schema.contracts.facts import FinancialFact

_DEFAULT_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "mock"


class FixtureFactRepository:
    """In-memory FactRepository over the ACME fixtures."""

    def __init__(self, fixtures_dir: str | Path | None = None) -> None:
        self.fixtures_dir = Path(fixtures_dir) if fixtures_dir else _DEFAULT_FIXTURES
        raw = json.loads((self.fixtures_dir / "facts.json").read_text(encoding="utf-8"))
        self._facts: list[FinancialFact] = [FinancialFact.model_validate(f) for f in raw]
        self._by_id: dict[str, FinancialFact] = {f.fact_id: f for f in self._facts}

    # ------------------------------------------------------------------
    # Visibility
    # ------------------------------------------------------------------
    def _effective_filed_at(self, fact: FinancialFact) -> str | None:
        """When this value first became knowable.

        A reported fact carries its own filing date. A DERIVED fact has none of
        its own, so it becomes visible only once every input it was computed
        from had been filed - otherwise a backtest could see a derived figure
        built from filings that did not exist yet.
        """
        if fact.filed_at:
            return fact.filed_at
        if fact.source_kind is SourceKind.DERIVED and fact.derivation:
            dates = [
                self._by_id[i].filed_at
                for i in fact.derivation.input_fact_ids
                if i in self._by_id and self._by_id[i].filed_at
            ]
            if dates:
                return max(dates)
        return None

    def _visible(self, fact: FinancialFact, as_of: ISODate | None) -> bool:
        """True when `fact` had been filed on or before `as_of`."""
        if not as_of:
            return True
        filed = self._effective_filed_at(fact)
        return filed is None or filed <= as_of

    @staticmethod
    def _group_key(fact: FinancialFact) -> tuple:
        """What makes two facts describe the same quantity."""
        dimension = tuple(sorted((fact.dimension or {}).items()))
        return (fact.company_id, fact.metric, fact.fiscal_period, fact.period_type, dimension)

    # ------------------------------------------------------------------
    # FactRepository
    # ------------------------------------------------------------------
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
        """Newest first, filed on or before `as_of`, restatements excluded.

        `include_superseded=True` returns the full history that was visible at
        `as_of` - which is how a restatement gets examined rather than hidden.
        """
        wanted = set(metrics)
        rows = [
            f
            for f in self._facts
            if f.company_id == ticker
            and f.metric in wanted
            and self._visible(f, as_of)
            and (period_type is None or f.period_type.value == period_type)
        ]

        if not include_superseded:
            # One row per quantity: whichever filing was most recent at `as_of`.
            latest: dict[tuple, FinancialFact] = {}
            for fact in rows:
                key = self._group_key(fact)
                current = latest.get(key)
                if current is None or (self._effective_filed_at(fact) or "") > (
                    self._effective_filed_at(current) or ""
                ):
                    latest[key] = fact
            rows = list(latest.values())

        rows.sort(
            key=lambda f: (f.period_end, self._effective_filed_at(f) or ""), reverse=True
        )
        return rows[:periods] if periods else rows

    def resolve_fact(self, fact_id: FactId, as_of: ISODate) -> FinancialFact | None:
        """One fact by id, or None when it does not exist or post-dates `as_of`."""
        fact = self._by_id.get(fact_id)
        if fact is None or not self._visible(fact, as_of):
            return None
        return fact

    def put_facts(self, facts: list[FinancialFact]) -> int:
        """The fixture store is read-only; live ingestion writes to Postgres."""
        raise NotImplementedError(
            "FixtureFactRepository is read-only. Regenerate the fixtures with "
            "`make gen-mock`, or use PostgresFactRepository in MODE=live."
        )

    def latest_period(
        self, ticker: Ticker, as_of: ISODate, *, annual: bool = True
    ) -> str | None:
        """Newest fiscal period label visible at `as_of`."""
        periods = [
            (f.period_end, f.fiscal_period)
            for f in self._facts
            if f.company_id == ticker
            and self._visible(f, as_of)
            and (not annual or f.fiscal_period.startswith("FY"))
        ]
        return max(periods)[1] if periods else None

    # ------------------------------------------------------------------
    # Beyond the Protocol
    # ------------------------------------------------------------------
    def lookup_regardless_of_date(self, fact_id: FactId) -> FinancialFact | None:
        """The fact if it exists at all, ignoring `as_of`.

        The `resolve_fact` TOOL needs this to tell three cases apart: the id does
        not exist (UNRESOLVED_FACT), it exists but was restated (SUPERSEDED_FACT),
        or it exists but post-dates the run (FUTURE_FACT). Collapsing those into
        a bare None would make the verifier's report useless
        (docs/verification.md). The Protocol method above keeps its documented
        contract.
        """
        return self._by_id.get(fact_id)

    def is_visible_at(self, fact_id: FactId, as_of: ISODate | None) -> bool:
        """Whether `fact_id` had been filed by `as_of`."""
        fact = self._by_id.get(fact_id)
        return fact is not None and self._visible(fact, as_of)
