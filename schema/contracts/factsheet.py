"""Factsheet - P1's deliverable, the input to everything else.

Specified by docs/data-model.md. PRODUCED BY data.api.build_factsheet.
CONSUMED BY calc/, audit/ and the orchestrator.

Contains REPORTED values only. P1 never computes a margin, an FCF or a ratio -
that is calc/'s job (ADR 0001). Filing TEXT is not inlined; fetch it with
data.api.get_filing_section(section_id).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schema.contracts.common import (
    DataQuality,
    ISODate,
    ISOTimestamp,
    Period,
    SchemaVersion,
    Scope,
    SourceId,
    SourceRef,
    Ticker,
    ValueObject,
)
from schema.contracts.enums import FilingType, Mode
from schema.contracts.filings import FilingSection
from schema.contracts.market import MarketSnapshot, NewsItem, Peer


class FinancialPeriod(BaseModel):
    """One reported fiscal period. Every line item is as-filed, never computed.

    Sign conventions (CLAUDE.md): capex is POSITIVE meaning cash spent;
    FCF = op_cash_flow - capex is calc/'s job, not this model's.
    """

    model_config = ConfigDict(extra="allow")

    period: Period
    period_end: ISODate
    form: FilingType
    filed_date: ISODate
    accession: str

    revenue: ValueObject
    cost_of_revenue: ValueObject
    gross_profit: ValueObject
    operating_income: ValueObject
    pretax_income: ValueObject
    net_income: ValueObject
    eps_diluted: ValueObject
    shares_diluted: ValueObject
    depreciation_amortization: ValueObject
    op_cash_flow: ValueObject
    capex: ValueObject = Field(description="POSITIVE number meaning cash spent.")
    sbc: ValueObject
    cash: ValueObject
    total_debt: ValueObject
    interest_expense: ValueObject
    total_assets: ValueObject
    total_equity: ValueObject
    current_assets: ValueObject
    current_liabilities: ValueObject
    receivables: ValueObject
    inventory: ValueObject


class SP500Baseline(BaseModel):
    """What the index costs today, so relative valuation has a reference point."""

    model_config = ConfigDict(extra="allow")

    forward_pe: ValueObject
    earnings_yield: ValueObject
    risk_free_rate: ValueObject
    as_of: ISODate


class Consensus(BaseModel):
    """Sell-side forecasts. Always type 'estimate', never 'fact'."""

    model_config = ConfigDict(extra="allow")

    revenue_next_fy: ValueObject | None = None
    eps_next_fy: ValueObject | None = None


class Factsheet(BaseModel):
    """The whole reported picture of one company at one as_of date."""

    model_config = ConfigDict(extra="allow")

    schema_version: SchemaVersion
    ticker: Ticker
    company_name: str = Field(min_length=1)
    as_of: ISODate = Field(
        description="AUTHORITATIVE for the run. Functions taking a factsheet must "
        "not also take an as_of (decision: amendment 2)."
    )
    built_at: ISOTimestamp
    mode: Mode

    scope: Scope
    data_quality: DataQuality

    market: MarketSnapshot
    financials: list[FinancialPeriod] = Field(
        min_length=1, description="One entry per period, NEWEST FIRST."
    )
    peers: list[Peer] = Field(default_factory=list)
    sp500_baseline: SP500Baseline
    consensus: Consensus | None = None

    filing_sections: list[FilingSection] = Field(
        default_factory=list,
        description="Section metadata only. Text is fetched by section_id.",
    )
    news: list[NewsItem] = Field(default_factory=list)
    sources: dict[SourceId, SourceRef] = Field(
        description="Registry of every source_id used anywhere in this fact sheet."
    )

    @model_validator(mode="after")
    def _check_periods_newest_first(self) -> Factsheet:
        ends = [p.period_end for p in self.financials]
        if ends != sorted(ends, reverse=True):
            raise ValueError(f"financials must be newest first, got period_end order {ends}")
        return self

    @model_validator(mode="after")
    def _check_point_in_time(self) -> Factsheet:
        """Nothing filed after as_of may appear (ADR 0003)."""
        late = [p.period for p in self.financials if p.filed_date > self.as_of]
        if late:
            raise ValueError(
                f"point-in-time violation: periods {late} were filed after as_of {self.as_of}"
            )
        late_sections = [s.section_id for s in self.filing_sections if s.filed_at > self.as_of]
        if late_sections:
            raise ValueError(
                f"point-in-time violation: sections {late_sections} filed after as_of "
                f"{self.as_of}"
            )
        return self

    @model_validator(mode="after")
    def _check_source_ids_resolve(self) -> Factsheet:
        """Every citation must land in `sources`, or provenance is a dead link."""
        known = set(self.sources)
        missing: list[str] = []
        for section in self.filing_sections:
            if section.source_id not in known:
                missing.append(f"filing_sections/{section.section_id}: {section.source_id}")
        for item in self.news:
            if item.source_id not in known:
                missing.append(f"news/{item.headline[:30]}: {item.source_id}")
        if missing:
            raise ValueError("source_id does not resolve in sources: " + "; ".join(missing))
        return self

    def period(self, label: str) -> FinancialPeriod | None:
        """Look up one reported period by its label, e.g. "FY2025"."""
        return next((p for p in self.financials if p.period == label), None)

    @property
    def latest_annual_period(self) -> str | None:
        """Newest full year. Flow metrics use this (never a trailing-quarter mix)."""
        return next((p.period for p in self.financials if p.period.startswith("FY")), None)

    @property
    def latest_balance_period(self) -> str:
        """Newest reported balance sheet, quarterly or annual."""
        return self.financials[0].period
