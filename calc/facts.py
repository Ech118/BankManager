"""The fact ledger: read a Factsheet's reported facts, emit calc/'s derived ones.

Specified by ADR 0002 (financial truth layer) and docs/verification.md.

`compute_metrics` produces two things at once: the `Metrics` object a reader
sees, and a list of derived `FinancialFact`s the verifier can recompute. This
module is what keeps the two in step - every ValueObject `emit()` returns is
backed by a derived fact with a formula, its input fact_ids, and a `filed_at`
that is the latest of its inputs.

Where the input fact_ids come from:

- P1's real factsheets carry them on each reported ValueObject, as
  `derived_from: ["fact:AAPL:revenue:FY2025"]`.
- The mock factsheet does not, so the id is rebuilt from the documented
  convention `fact:<TICKER>:<metric>:<PERIOD>` (fixtures/mock/facts.json).
- Market values (price, market cap, enterprise value) have no fact id anywhere,
  so the ledger MINTS one and publishes it in `metrics["input_facts"]`. Without
  that, half of calc/'s derived facts would cite inputs the verifier cannot
  resolve.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from calc.lineage import FactRef, derived_fact, derived_value

PARTIAL_SCOPE_KEYWORDS = ("bank", "insurer", "insurance", "reit", "broker")
"""Words in a scope reason that mean the standard metric set does not apply."""


def is_partial_scope(factsheet: dict) -> bool:
    """True for a bank, insurer, broker or REIT: in scope, but partially.

    P1 marks these `scope.level == "partial"` and attaches the reason as a gap.
    The keyword check is a fallback for a factsheet built before `level` existed.
    """
    scope = factsheet.get("scope") or {}
    if scope.get("level") == "partial":
        return True
    reason = (scope.get("reason") or "").lower()
    return bool(reason) and any(word in reason for word in PARTIAL_SCOPE_KEYWORDS)


def _date(stamp: str | None) -> str | None:
    """The date part of an ISO date or timestamp."""
    return stamp[:10] if stamp else None


def span_start(label: str, period_end: str) -> str:
    """The start of the period a label covers, from its end.

    `FinancialPeriod` records only `period_end`, but a derived DURATION fact
    needs a start, so it is reconstructed from the label: a year back for FY, a
    quarter back for Q. Provenance-grade precision is not needed here - the
    fiscal_period label is what a reader cites.
    """
    end = date.fromisoformat(period_end)
    months = 12 if label.startswith("FY") else 3
    year = end.year - (months // 12)
    month = end.month - (months % 12)
    if month <= 0:
        month += 12
        year -= 1
    day = min(
        end.day,
        [31, 29 if year % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1],
    )
    return date(year, month, day).isoformat()


class Ledger:
    """Resolves reported facts and accumulates the derived ones for one run."""

    def __init__(self, factsheet: dict) -> None:
        self.factsheet = factsheet
        self.ticker: str = factsheet["ticker"]
        self.as_of: str = factsheet["as_of"]
        self.retrieved_at: str = factsheet.get("built_at") or f"{self.as_of}T00:00:00Z"
        self.periods: dict[str, dict] = {p["period"]: p for p in factsheet.get("financials", [])}
        self.market: dict = factsheet.get("market") or {}
        self.market_date: str = _date(self.market.get("as_of")) or self.as_of
        self._minted: dict[str, dict] = {}
        self._derived: list[dict] = []
        self._by_id: dict[str, dict] = {}
        self._notes: list[str] = []

    # ----------------------------------------------------------------- inputs
    def ref(self, period_label: str, field: str) -> FactRef | None:
        """A reported line item, as an input reference. None when unavailable."""
        period = self.periods.get(period_label)
        if not period:
            return None
        vo = period.get(field)
        if not isinstance(vo, dict) or vo.get("status") != "ok" or vo.get("value") is None:
            return None
        return FactRef(
            fact_id=self._reported_fact_id(vo, field, period_label),
            metric=field,
            period=period_label,
            value=float(vo["value"]),
            filed_at=period.get("filed_date"),
        )

    def _reported_fact_id(self, vo: dict, field: str, period_label: str) -> str:
        for candidate in vo.get("derived_from") or []:
            if isinstance(candidate, str) and candidate.startswith("fact:"):
                return candidate
        return f"fact:{self.ticker}:{field}:{period_label}"

    def market_ref(self, field: str, *, kind: str = "market_api") -> FactRef | None:
        """A market snapshot value, minting a fact id the verifier can resolve."""
        vo = self.market.get(field)
        return self._mint(vo, field, f"market.{field}", kind)

    def top_level_ref(self, block: str, field: str, *, kind: str = "estimate") -> FactRef | None:
        """A value from `consensus` or `sp500_baseline`, minted the same way."""
        container = self.factsheet.get(block) or {}
        vo = container.get(field) if isinstance(container, dict) else None
        return self._mint(vo, f"{block}_{field}", f"{block}.{field}", kind)

    def _mint(self, vo: Any, metric: str, location: str, kind: str) -> FactRef | None:
        if not isinstance(vo, dict) or vo.get("status") != "ok" or vo.get("value") is None:
            return None
        for candidate in vo.get("derived_from") or []:
            if isinstance(candidate, str) and candidate.startswith("fact:"):
                # P1 already published this one; cite it rather than minting a twin.
                return FactRef(candidate, metric, self.as_of, float(vo["value"]), self.market_date)
        fact_id = f"fact:{self.ticker}:{metric}:{self.market_date}"
        if fact_id not in self._minted:
            self._minted[fact_id] = {
                "fact_id": fact_id,
                "company_id": self.ticker,
                "metric": metric,
                "value": float(vo["value"]),
                "unit": vo.get("unit", "usd"),
                "currency": "USD" if vo.get("unit") in ("usd", "usd_per_share") else None,
                "period_type": "instant",
                "period_end": self.market_date,
                "fiscal_period": vo.get("fiscal_period") or self.latest_annual_label() or "FY0000",
                "filed_at": self.market_date,
                "retrieved_at": self.market.get("retrieved_at") or self.retrieved_at,
                "source_url": vo.get("source_url"),
                "source_location": location,
                "source_kind": kind,
            }
        return FactRef(fact_id, metric, self.as_of, float(vo["value"]), self.market_date)

    # ---------------------------------------------------------------- periods
    def latest_annual_label(self) -> str | None:
        for label in self.periods:
            if label.startswith("FY"):
                return label
        return None

    def annual_labels(self) -> list[str]:
        """Annual period labels, newest first."""
        return [label for label in self.periods if label.startswith("FY")]

    # ----------------------------------------------------------------- output
    def emit(
        self,
        num: float | None,
        *,
        metric: str,
        period: str,
        unit: str,
        formula: str,
        inputs: dict[str, FactRef],
        paths: list[str],
        value_type: str = "fact",
        reason: str | None = None,
        not_applicable: bool = False,
        period_type: str | None = None,
        source_id: str | None = None,
        derivation_extra: dict[str, Any] | None = None,
    ) -> dict:
        """Return the ValueObject, recording a derived fact when there is a value.

        `num=None` yields an unavailable ValueObject carrying `reason` and no
        fact: an unavailable metric is not a fact with a null in it.
        """
        if num is None:
            return derived_value(
                None,
                unit,
                paths,
                value_type=value_type,
                reason=reason,
                not_applicable=not_applicable,
            )
        fact_id = f"fact:{self.ticker}:{metric}:{period}"
        if fact_id in self._by_id:
            # Emitted already (a flag recomputing a metric it also reports).
            # One fact per id, and the first one wins: two facts with the same id
            # and different provenance is the failure this guards against.
            return derived_value(
                num, unit, paths, value_type=value_type, fact_id=fact_id, source_id=source_id
            )
        window = sorted({ref.period for ref in inputs.values() if ref.period in self.periods})
        if period_type is None:
            period_type = "duration" if period.startswith(("FY", "Q")) else "instant"
        ends = [self.periods[label]["period_end"] for label in window] or [self.as_of]
        period_end = self.periods.get(period, {}).get("period_end") or max(ends)
        period_start = None
        if period_type == "duration":
            spans = [span_start(label, self.periods[label]["period_end"]) for label in window]
            period_start = min(spans) if spans else span_start(period, period_end)
            period_start = min(period_start, period_end)
        fact = derived_fact(
            metric,
            formula,
            inputs,
            num,
            company_id=self.ticker,
            period=period,
            period_end=period_end,
            period_type=period_type,
            period_start=period_start,
            unit=unit,
            retrieved_at=self.retrieved_at,
            fact_id=fact_id,
            derivation_extra=derivation_extra,
        )
        self._derived.append(fact)
        self._by_id[fact_id] = fact
        return derived_value(
            num,
            unit,
            paths,
            value_type=value_type,
            fact_id=fact_id,
            source_id=source_id,
        )

    def adopt(self, facts: list[dict]) -> None:
        """Index facts an earlier ledger produced, without re-publishing them.

        `calculate_valuation` builds its extra blocks on a second ledger, and those
        blocks cite metrics the first one emitted (a peer premium cites this
        company's P/E). Adopting the facts lets `derived_ref` find them, so the
        lineage - and with it the filed_at chain - stays intact across the two.
        """
        for fact in facts:
            self._by_id.setdefault(fact["fact_id"], fact)

    def derived_ref(self, vo: dict | None, metric: str = "") -> FactRef | None:
        """Turn a ValueObject calc/ already emitted back into an input reference.

        This is what makes the filed_at rule compose: a fact derived from derived
        facts still ends up with the date its last RAW input was filed.
        """
        if not isinstance(vo, dict) or vo.get("status") != "ok":
            return None
        fact_id = vo.get("fact_id")
        fact = self._by_id.get(fact_id) if fact_id else None
        if fact is None:
            return None
        return FactRef(
            fact_id=fact["fact_id"],
            metric=fact["metric"] or metric,
            period=fact["fiscal_period"],
            value=fact["value"],
            filed_at=fact.get("filed_at"),
        )

    def note(self, text: str) -> None:
        """Record why a metric was skipped, so the report can say so."""
        if text not in self._notes:
            self._notes.append(text)

    @property
    def derived_facts(self) -> list[dict]:
        return self._derived

    @property
    def input_facts(self) -> list[dict]:
        """Market and consensus facts calc/ had to mint an id for."""
        return list(self._minted.values())

    @property
    def notes(self) -> list[str]:
        return list(self._notes)


def missing_reason(inputs: dict[str, Any], period: str | None = None) -> str:
    """Name the inputs that were unavailable, so the report can say which ones."""
    missing = [name for name, ref in inputs.items() if ref is None]
    where = f" for {period}" if period else ""
    if not missing:
        return f"the formula is undefined for these inputs{where} (a zero or negative base)"
    return f"{', '.join(missing)} unavailable{where}"


def present(inputs: dict[str, Any]) -> dict[str, Any]:
    """Only the inputs that resolved. Used when every one of them did."""
    return {name: ref for name, ref in inputs.items() if ref is not None}


def nums(inputs: dict[str, Any]) -> dict[str, float | None]:
    """The numeric value of each input, None where it is missing."""
    return {name: (None if ref is None else ref.value) for name, ref in inputs.items()}
