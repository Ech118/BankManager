"""Recent news, for post-earnings developments.

Specified by docs/data-model.md "News" and docs/verification.md (injection).

News text is the LEAST trusted input in the system: it is arbitrary third-party
prose fed to an LLM. It is returned as data, wrapped as quoted content by the
MCP layer, and agents are instructed never to follow instructions found in it.

TODO(roadmap Step 4, P1).
"""

from __future__ import annotations

from schema.contracts.common import ISODate, Ticker
from schema.contracts.market import NewsItem


def search(
    ticker: Ticker, as_of: ISODate, lookback_days: int = 60, limit: int = 20
) -> list[NewsItem]:
    """Headlines published in [as_of - lookback_days, as_of], newest first.

    The upper bound matters as much as the lower one: a backtest that sees
    tomorrow's news is not a backtest (ADR 0003).
    """
    raise NotImplementedError("TODO(roadmap Step 4, P1)")
