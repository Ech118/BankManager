"""Metrics - P2's deterministic output. Every number here is computed in code.

Specified by docs/data-model.md. PRODUCED BY calc.api.compute_metrics.
CONSUMED BY P3 agents (through MCP) and by audit/.

No LLM ever writes into this model (ADR 0001). Every leaf is a ValueObject with
type 'fact' plus `derived_from`, or type 'assumption' with a src:config: source.

Flow metrics use the latest FULL YEAR (`latest_annual_period`); balance-sheet
metrics use the latest reported balance sheet (`latest_balance_period`).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from schema.contracts.common import (
    ISODate,
    Period,
    SchemaVersion,
    Ticker,
    ValueObject,
)
from schema.contracts.enums import FlagSeverity


class Margins(BaseModel):
    """Profitability at one period. Fractions, never percents."""

    model_config = ConfigDict(extra="allow")

    gross: ValueObject
    operating: ValueObject
    net: ValueObject
    fcf: ValueObject


class Growth(BaseModel):
    """Year-over-year change. Only emitted where a prior comparable period exists."""

    model_config = ConfigDict(extra="allow")

    revenue_yoy: ValueObject
    eps_yoy: ValueObject
    fcf_yoy: ValueObject


class CashFlow(BaseModel):
    """Cash generation. `ebitda` is unadjusted on purpose: operating income + D&A."""

    model_config = ConfigDict(extra="allow")

    fcf: ValueObject = Field(description="op_cash_flow - capex.")
    fcf_conversion: ValueObject = Field(description="FCF / net income.")
    fcf_yield: ValueObject = Field(description="FCF / market cap.")
    capex_intensity: ValueObject = Field(description="Capex / revenue.")
    ebitda: ValueObject = Field(description="Operating income + D&A, UNADJUSTED.")


class BalanceSheet(BaseModel):
    model_config = ConfigDict(extra="allow")

    net_debt: ValueObject = Field(description="Positive when debt exceeds cash.")
    net_debt_to_ebitda: ValueObject
    interest_coverage: ValueObject = Field(description="Operating income / interest expense.")
    current_ratio: ValueObject


class PerShare(BaseModel):
    """Dilution and stock-based compensation, the two ways per-share results drift."""

    model_config = ConfigDict(extra="allow")

    dilution_yoy: ValueObject = Field(
        description="Change in diluted shares; negative means a shrinking share count."
    )
    sbc_pct_revenue: ValueObject
    sbc_pct_fcf: ValueObject


class QualityFlag(BaseModel):
    """A deterministic earnings-quality warning raised by calc/, not by an agent."""

    model_config = ConfigDict(extra="allow")

    flag: str = Field(min_length=1, description="Machine-readable id, e.g. dso_rising.")
    detail: str = Field(min_length=1, description="What was observed, with numbers.")
    severity: FlagSeverity


class VsPeers(BaseModel):
    """Premium (+) or discount (-) to the peer MEDIAN, as fractions."""

    model_config = ConfigDict(extra="allow")

    pe_premium: ValueObject
    ev_ebitda_premium: ValueObject


class VsSP500(BaseModel):
    model_config = ConfigDict(extra="allow")

    forward_pe_premium: ValueObject


class Valuation(BaseModel):
    model_config = ConfigDict(extra="allow")

    pe: ValueObject
    forward_pe: ValueObject
    ev_ebitda: ValueObject
    ev_revenue: ValueObject
    p_fcf: ValueObject
    vs_peers: VsPeers
    vs_sp500: VsSP500


class DcfAssumptions(BaseModel):
    """Tagged ASSUMPTION so the report colour-codes them (error D)."""

    model_config = ConfigDict(extra="allow")

    discount_rate: ValueObject
    terminal_growth: ValueObject
    horizon_years: int = Field(ge=1)


class SensitivityRow(BaseModel):
    """One cell of the sensitivity grid. Bare numbers here are a documented exception."""

    model_config = ConfigDict(extra="allow")

    discount_rate: float
    terminal_growth: float
    implied_fcf_cagr: ValueObject


class ReverseDcf(BaseModel):
    """What growth the current price already implies.

    A single point answer would be misleading, so `sensitivity_grid` is required
    and must never be empty (error D, ADR 0001).
    """

    model_config = ConfigDict(extra="allow")

    implied_fcf_cagr: ValueObject = Field(
        description="Annual FCF growth over the horizon implied by today's price."
    )
    assumptions: DcfAssumptions
    sensitivity_grid: list[SensitivityRow] = Field(
        min_length=1, description="Never a single point answer."
    )


class Metrics(BaseModel):
    """Everything calc.compute_metrics derives from one Factsheet."""

    model_config = ConfigDict(extra="allow")

    schema_version: SchemaVersion
    ticker: Ticker
    as_of: ISODate = Field(description="Copied from the factsheet; never passed separately.")
    latest_annual_period: Period
    latest_balance_period: Period

    margins: dict[Period, Margins] = Field(description="period -> margins.")
    growth: dict[Period, Growth] = Field(description="period -> year-over-year growth.")
    cash_flow: CashFlow
    balance_sheet: BalanceSheet
    per_share: PerShare
    quality_flags: list[QualityFlag] = Field(default_factory=list)
    valuation: Valuation
    reverse_dcf: ReverseDcf
