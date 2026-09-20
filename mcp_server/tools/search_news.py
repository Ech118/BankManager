"""MCP tool: search_news. Wraps data.api.search_news.

Specified by docs/mcp-tools.md#search_news.

Purpose: post-earnings developments - what happened since the last filing. This
is the LEAST trusted input in the system: arbitrary third-party prose, returned
as data and wrapped as quoted content, and agents are told that instructions
found inside it are data about a document, not directions (ADR 0005).

`as_of` bounds the window from ABOVE as well as below. A run dated June that
reads September headlines has been told the answer.

Errors: ValueError for an out-of-scope ticker. An empty list is a valid answer,
and a provider outage produces one plus a data_quality gap rather than a
failure - an agent that gets an exception aborts its turn, while an agent that
gets no news reasons about a company with no recent news.
as_of: required.
"""

from __future__ import annotations

from typing import Any

from mcp_server.backends import require_in_scope
from schema.contracts.market import NewsItem
from schema.contracts.tools import SearchNewsRequest, SearchNewsResponse


def run(request: SearchNewsRequest, backends: Any) -> SearchNewsResponse:
    require_in_scope(request.ticker, request.as_of)

    from data import api as data_api

    raw = data_api.search_news(
        request.ticker,
        request.as_of,
        lookback_days=request.lookback_days,
        limit=request.limit,
    )
    return SearchNewsResponse(
        as_of=request.as_of,
        news=[NewsItem.model_validate(item) for item in raw],
        truncated=len(raw) >= request.limit,
    )
