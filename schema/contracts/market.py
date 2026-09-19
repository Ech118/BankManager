"""Market-side contracts: snapshot, company profile, peers, news.

Specified by docs/data-model.md. Produced by P1 (data/); consumed by P2 for
valuation inputs and by P3 through MCP tools.

Every field on MarketSnapshot is observed at ONE `as_of` timestamp. Mixing a
price from today with a share count from last quarter is how enterprise value
silently goes wrong, so the timestamp lives on the snapshot, not on the fields.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schema.contracts.common import (
    ISODate,
    ISOTimestamp,
    SourceId,
    Ticker,
    ValueObject,
)


class MarketSnapshot(BaseModel):
    """Price, share count and the EV bridge, all observed at one instant.

    `enterprise_value` is a derived convenience: market_cap + total_debt - cash.
    calc/ recomputes it and the verifier raises RECOMPUTE_MISMATCH on drift.
    """

    model_config = ConfigDict(extra="allow")

    ticker: Ticker
    as_of: ISOTimestamp = Field(
        description="The single instant every field below was observed at."
    )
    retrieved_at: ISOTimestamp
    source_id: SourceId

    price: ValueObject
    shares_outstanding: ValueObject
    market_cap: ValueObject

    total_debt: ValueObject = Field(description="EV bridge input, from the latest balance sheet.")
    cash: ValueObject = Field(description="Cash and equivalents, EV bridge input.")
    enterprise_value: ValueObject

    currency: str = "USD"


class CompanyProfile(BaseModel):
    """Identity and classification. `sic` drives check_scope and peer selection."""

    model_config = ConfigDict(extra="allow")

    ticker: Ticker
    company_name: str = Field(min_length=1)
    cik: str | None = None
    sic: str | None = Field(default=None, description="SEC SIC code; 6xxx implies financials.")
    sic_description: str | None = None
    exchange: str | None = None
    fiscal_year_end: str | None = Field(
        default=None, description='MM-DD, e.g. "12-31". Drives Q4 derivation.'
    )
    as_of: ISODate
    retrieved_at: ISOTimestamp
    source_id: SourceId


class Peer(BaseModel):
    """One comparable company. Peer multiples are the weakest data we carry (error E),
    so every field is a ValueObject that may legitimately be `unavailable`."""

    model_config = ConfigDict(extra="allow")

    ticker: Ticker
    company_name: str | None = None
    sic: str | None = None
    market_cap: ValueObject
    pe: ValueObject
    ev_ebitda: ValueObject
    ev_revenue: ValueObject
    fcf_yield: ValueObject
    selection_reason: str | None = Field(
        default=None, description="Why this peer was chosen. The Valuation Agent must justify it."
    )


class NewsItem(BaseModel):
    """One post-earnings development. Treated strictly as untrusted DATA by agents."""

    model_config = ConfigDict(extra="allow")

    headline: str = Field(min_length=1)
    date: ISODate
    url: str
    source_id: SourceId
    snippet: str | None = None

    @model_validator(mode="after")
    def _check_url(self) -> NewsItem:
        if self.url and not self.url.startswith(("http://", "https://")):
            raise ValueError(f"news url must be absolute, got {self.url!r}")
        return self
